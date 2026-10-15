function W = star_read_passes(csvfile, sat_index, imaging_purpose, sim_start)
% STAR_READ_PASSES  Finestre dei pass di IMAGING per un satellite [s dal sim start].
%   Legge selected_pass_summary.csv e restituisce W = [t_on t_off] (Nx2, secondi
%   dall'inizio simulazione) per i pass il cui "purpose" inizia con imaging_purpose.
T = readtable(csvfile,'TextType','string','Delimiter',',');
fmt = 'yyyy-MM-dd''T''HH:mm:ss''Z''';
W = zeros(0,2);
for i = 1:height(T)
    if T.satellite_index(i)==sat_index && startsWith(lower(T.purpose(i)), lower(imaging_purpose))
        ts = datetime(T.start_utc(i),'InputFormat',fmt,'TimeZone','UTC');
        te = datetime(T.end_utc(i),  'InputFormat',fmt,'TimeZone','UTC');
        W(end+1,:) = [seconds(ts-sim_start), seconds(te-sim_start)]; %#ok<AGROW>
    end
end
end
