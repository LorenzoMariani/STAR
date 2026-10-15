function cdm = parseCDMcara(filename)


if nargin < 1
    error('readCDM requires a filename.');
end

filename = char(filename);
txt = fileread(filename);
lines = regexp(txt, '\r\n|\n|\r', 'split');

cdm = struct();
cdm.FileName = filename;
cdm.RawLines = lines(:);
cdm.Header = struct();
cdm.Header.Comments = emptyCommentArray();
cdm.Header.CommentFields = struct();
cdm.Objects = struct([]);
cdm.Unparsed = struct('LineNumber', {}, 'RawLine', {});

currentObject = 0;

for i = 1:numel(lines)
    rawLine = lines{i};
    line = strtrim(rawLine);

    if isempty(line)
        continue;
    end

    % COMMENT lines
    if strncmp(line, 'COMMENT', numel('COMMENT'))
        commentText = strtrim(line(numel('COMMENT')+1:end));
        entry = parseComment(commentText, i, rawLine);

        if currentObject == 0
            cdm.Header = addCommentToSection(cdm.Header, entry);
        else
            cdm.Objects(currentObject) = addCommentToObject(cdm.Objects(currentObject), entry);
        end

        continue;
    end

    % Normal KEY = VALUE lines
    tok = regexp(line, '^([^=]+?)\s*=\s*(.*)$', 'tokens', 'once');

    if isempty(tok)
        cdm.Unparsed(end+1) = struct( ...
            'LineNumber', i, ...
            'RawLine', rawLine);
        continue;
    end

    key = strtrim(tok{1});
    rhs = strtrim(tok{2});
    entry = makeEntry(key, rhs, i, rawLine);

    % A new OBJECT line starts a new object block
    if strcmpi(key, 'OBJECT')
        currentObject = currentObject + 1;

        cdm.Objects(currentObject).Comments = emptyCommentArray();
        cdm.Objects(currentObject).CommentFields = struct();

        cdm.Objects(currentObject).OBJECT = entry;
        continue;
    end

    if currentObject == 0
        fname = uniqueFieldName(cdm.Header, entry.FieldName);
        entry.FieldName = fname;
        cdm.Header.(fname) = entry;
    else
        fname = uniqueFieldName(cdm.Objects(currentObject), entry.FieldName);
        entry.FieldName = fname;
        cdm.Objects(currentObject).(fname) = entry;
    end
end

cdm = addDerivedFields(cdm);
end

function entry = makeEntry(key, rhs, lineNumber, rawLine)
[value, unit] = parseValueAndUnit(rhs);

entry = struct( ...
    'Key', {key}, ...
    'FieldName', {matlab.lang.makeValidName(key)}, ...
    'Value', {value}, ...
    'Unit', {unit}, ...
    'Raw', {rhs}, ...
    'LineNumber', {lineNumber}, ...
    'RawLine', {rawLine});
end

function entry = parseComment(commentText, lineNumber, rawLine)
tok = regexp(commentText, '^([^=]+?)\s*=\s*(.*)$', 'tokens', 'once');

if isempty(tok)
    key = sprintf('Comment_%d', lineNumber);
    rhs = commentText;
else
    key = strtrim(tok{1});
    rhs = strtrim(tok{2});
end

entry = makeEntry(key, rhs, lineNumber, rawLine);
end

function [value, unit] = parseValueAndUnit(rhs)
unit = '';
valueText = strtrim(rhs);

% Extract trailing unit in square brackets, e.g. 123 [m]
tok = regexp(valueText, '^(.*?)\s*\[([^\]]+)\]\s*$', 'tokens', 'once');

if ~isempty(tok)
    valueText = strtrim(tok{1});
    unit = strtrim(tok{2});
end

value = convertValue(valueText);
end

function value = convertValue(s)
s = strtrim(s);

if isempty(s)
    value = '';
    return;
end

% Preserve pure integer identifiers with leading zeros, e.g. 000020580
if ~isempty(regexp(s, '^0\d+$', 'once'))
    value = s;
    return;
end

% ISO-like datetime, e.g. 2023-06-13T00:19:23.766
if ~isempty(regexp(s, '^\d{4}-\d{2}-\d{2}T', 'once'))
    fmts = { ...
        'yyyy-MM-dd''T''HH:mm:ss.SSS', ...
        'yyyy-MM-dd''T''HH:mm:ss'};

    for k = 1:numel(fmts)
        try
            value = datetime(s, 'InputFormat', fmts{k});
            return;
        catch
        end
    end
end

% Numeric scalar or vector
numRe = '[+-]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eEdD][+-]?\d+)?';
matches = regexp(s, numRe, 'match');

if ~isempty(matches)
    leftover = regexprep(s, numRe, '');
    leftover = regexprep(leftover, '[\s,;]+', '');

    if isempty(leftover)
        matches = strrep(matches, 'D', 'E');
        matches = strrep(matches, 'd', 'e');
        value = str2double(matches);

        if numel(value) == 1
            value = value(1);
        end

        return;
    end
end

% Otherwise keep as text
value = s;
end

function comments = emptyCommentArray()
comments = struct( ...
    'Key', {}, ...
    'FieldName', {}, ...
    'Value', {}, ...
    'Unit', {}, ...
    'Raw', {}, ...
    'LineNumber', {}, ...
    'RawLine', {});
end

function section = addCommentToSection(section, entry)
if ~isfield(section, 'Comments') || isempty(section.Comments)
    section.Comments = emptyCommentArray();
end

section.Comments(end+1) = entry;

if ~isfield(section, 'CommentFields') || isempty(section.CommentFields)
    section.CommentFields = struct();
end

fname = uniqueFieldName(section.CommentFields, entry.FieldName);
entry.FieldName = fname;
section.CommentFields.(fname) = entry;
end

function obj = addCommentToObject(obj, entry)
if ~isfield(obj, 'Comments') || isempty(obj.Comments)
    obj.Comments = emptyCommentArray();
end

obj.Comments(end+1) = entry;

if ~isfield(obj, 'CommentFields') || isempty(obj.CommentFields)
    obj.CommentFields = struct();
end

fname = uniqueFieldName(obj.CommentFields, entry.FieldName);
entry.FieldName = fname;
obj.CommentFields.(fname) = entry;
end

function fname = uniqueFieldName(section, base)
fname = base;
n = 2;

while isfield(section, fname) && ~isempty(section.(fname))
    fname = sprintf('%s_%d', base, n);
    n = n + 1;
end
end

function cdm = addDerivedFields(cdm)
% Convenience relative state from the header
rel = struct();

if hasNumericEntry(cdm.Header, 'RELATIVE_POSITION_R') && ...
        hasNumericEntry(cdm.Header, 'RELATIVE_POSITION_T') && ...
        hasNumericEntry(cdm.Header, 'RELATIVE_POSITION_N')

    rel.PositionRTN_m = [ ...
        cdm.Header.RELATIVE_POSITION_R.Value, ...
        cdm.Header.RELATIVE_POSITION_T.Value, ...
        cdm.Header.RELATIVE_POSITION_N.Value];
end

if hasNumericEntry(cdm.Header, 'RELATIVE_VELOCITY_R') && ...
        hasNumericEntry(cdm.Header, 'RELATIVE_VELOCITY_T') && ...
        hasNumericEntry(cdm.Header, 'RELATIVE_VELOCITY_N')

    rel.VelocityRTN_m_s = [ ...
        cdm.Header.RELATIVE_VELOCITY_R.Value, ...
        cdm.Header.RELATIVE_VELOCITY_T.Value, ...
        cdm.Header.RELATIVE_VELOCITY_N.Value];
end

if ~isempty(fieldnames(rel))
    cdm.Relative = rel;
end

% Convenience state and covariance per object
for k = 1:numel(cdm.Objects)
    obj = cdm.Objects(k);

    state = struct();

    if hasNumericEntry(obj, 'X') && ...
            hasNumericEntry(obj, 'Y') && ...
            hasNumericEntry(obj, 'Z')

        state.Position_km = [ ...
            obj.X.Value, ...
            obj.Y.Value, ...
            obj.Z.Value];
    end

    if hasNumericEntry(obj, 'X_DOT') && ...
            hasNumericEntry(obj, 'Y_DOT') && ...
            hasNumericEntry(obj, 'Z_DOT')

        state.Velocity_km_s = [ ...
            obj.X_DOT.Value, ...
            obj.Y_DOT.Value, ...
            obj.Z_DOT.Value];
    end

    if ~isempty(fieldnames(state))
        cdm.Objects(k).State = state;
    end

    [C, found] = buildRTNCovariance(obj);

    if found
        cov = struct();
        cov.Value = C;
        cov.Frame = 'RTN';
        cov.StateOrder = {'R', 'T', 'N', 'RDOT', 'TDOT', 'NDOT'};
        cov.Description = '6x6 covariance in RTN state order [R T N RDOT TDOT NDOT]. Units are mixed; see individual covariance entries.';

        cdm.Objects(k).CovarianceRTN = cov;
    end
end
end

function tf = hasNumericEntry(s, fieldName)
tf = isfield(s, fieldName) && ...
    isstruct(s.(fieldName)) && ...
    isfield(s.(fieldName), 'Value') && ...
    isnumeric(s.(fieldName).Value);
end

function [C, found] = buildRTNCovariance(obj)
labels = {'R', 'T', 'N', 'RDOT', 'TDOT', 'NDOT'};
rowPrefixes = {'CR', 'CT', 'CN', 'CRDOT', 'CTDOT', 'CNDOT'};

C = nan(6, 6);
found = false;

for r = 1:6
    for c = 1:r
        fieldName = [rowPrefixes{r}, '_', labels{c}];

        if hasNumericEntry(obj, fieldName)
            C(r, c) = obj.(fieldName).Value;
            C(c, r) = obj.(fieldName).Value;
            found = true;
        end
    end
end
end