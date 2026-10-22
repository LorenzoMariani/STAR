function C = star_hot_case(cfg, orb, cs, bmin, bmax)
% STAR_HOT_CASE  Hot design case: the beta of the mission life that gives the hottest battery (STAR phase D, 2026-10-22).
%   C = star_hot_case(cfg, orb, cs, bmin, bmax) runs star_design_case with the dissipation cs.P_internal_W
%   at every |beta| of the life range [bmin, bmax] (deg, END-001 eclipse_summary) on a 5 deg grid plus
%   the range ends, then refines on a 1 deg grid around the hottest one, and returns the case with the
%   highest battery maximum (central body when the model has no battery). The sign of beta does not
%   change the heat loads of the nadir attitude (the model is symmetric about the orbit plane), so
%   only |beta| is searched. The shortest eclipse (max |beta|) is not always the hottest: with body
%   panels on the side faces a lower beta can heat the battery more.
%   C: as star_design_case, plus .scan [n x 2] (|beta| deg, node maximum degC) and .rule.

lo = min(abs([bmin bmax])); hi = max(abs([bmin bmax]));
if bmin <= 0 && bmax >= 0, lo = 0; end
bgrid = unique([lo, ceil(lo/5)*5:5:hi, hi]);
[scan, best] = run_grid(cfg, orb, cs, bgrid, []);
k = find(bgrid == best.beta_deg, 1);
fine = unique(max(lo, min(hi, bgrid(max(1, k - 1)):1:bgrid(min(numel(bgrid), k + 1)))));
[scan, best] = run_grid(cfg, orb, cs, setdiff(fine, scan(:, 1)'), scan, best);
C = best;
C.scan = sortrows(scan, 1);
C.rule = sprintf('|beta| of the mission life (%.1f..%.1f deg) with the hottest %s', lo, hi, node_name(C));
end

function [scan, best] = run_grid(cfg, orb, cs, betas, scan, best)
if nargin < 6, best = []; end
for b = betas
    c = star_design_case(cfg, orb, struct('name', cs.name, 'beta_deg', b, 'P_internal_W', cs.P_internal_W));
    k = find(strcmp(c.names, node_name(c)), 1);
    scan(end+1, :) = [b, c.Tmax(k)]; %#ok<AGROW>
    if isempty(best) || c.Tmax(k) > best.Tmax(k), best = c; end
end
end

function n = node_name(c)
if any(strcmp(c.names, 'BAT')), n = 'BAT'; else, n = 'CTR'; end
end
