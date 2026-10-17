function info = end003_aem_figures(aemFile, opts)
%END003_AEM_FIGURES  Figures and rotational state that describe the attitude in a CCSDS AEM.
%
%   info = end003_aem_figures(aemFile, opts)
%
%   Reads an AEM of type QUATERNION/ANGVEL in the S5Lab layout (BILAR_DB,
%   STAR END-003): Q1 Q2 Q3 QC scalar last = rotation body -> J2000 (frame
%   transformation J2000 -> body), ANGVEL in the body frame [rad/s]. Writes in
%   opts.out_dir, with the file-name prefix opts.prefix, the figures made for
%   the Sentinel-1B attitude of the ERASE proposal (Figures 10-13, Table 9):
%     <prefix>_A_inertial_view.png      attitude at 8 epochs of the pass, fixed
%                                       inertial view with the angular momentum H vertical
%     <prefix>_B_view_along_H.png       same sequence seen along H, path of the tip of omega
%     <prefix>_C_H_orbital_plane.png    H and omega with respect to the orbit at mid pass
%                                       (only with opts.orbit_rv)
%     <prefix>_D_parameters.png         quaternion, ZYX Euler angles, body angular velocity
%     <prefix>_rotational_state.json    rotational state (Table 9 of the proposal)
%
%   opts fields (all optional except out_dir/prefix):
%     out_dir, prefix   output folder and file-name prefix
%     title             text of the figure titles (e.g. 'Imaging pass (END-007), SAT-04 over AOI point 12')
%     I                 inertia tensor in the body frame [kg m^2] (default identity: H = omega)
%     dims              [x y z] sides of the body drawn as a CubeSat [m] (default 3U)
%     mode              attitude mode, for the table
%     orbit_rv          @(ts datetime UTC) -> [r (n x 3, m), v (n x 3, m/s)] in the AEM inertial frame
%     gmst              @(ts datetime UTC) -> Greenwich sidereal angle [rad] (Earth drawing)
%     site, site_role   ground point drawn on the Earth (struct name, lat, lon [rad], alt [m]) and its role
%     frame_rot         3x3 rotation from the frame where ECEF = R3(GMST) x to the AEM frame (e.g. precession)
%
%   info.figures = struct array (file, title, caption); info.rotational_state =
%   struct array (quantity, value); info.values = numbers of the table.

    if nargin < 2, opts = struct(); end
    opts = defaults(opts);
    [ts, q, w] = read_aem(aemFile);
    n = numel(ts);
    t = seconds(ts - ts(1));
    R = zeros(3, 3, n);
    for i = 1:n, R(:, :, i) = qdcm(q(i, :)); end              % body -> J2000
    Hb = (opts.I*w')';                                          % body frame
    H = rot_rows(R, Hb);                                        % inertial
    W = rot_rows(R, w);
    Hmag = vecnorm(H, 2, 2);
    if max(Hmag) > 0
        Hm = sum(H, 1)/norm(sum(H, 1));
    else
        Hm = [0 0 1];
    end
    stats = rotational_state(t, ts, R, w, W, H, Hb, Hm, opts);

    figs = struct('file', {}, 'title', {}, 'caption', {});
    % 8 epochs over the pass or, when the body turns about H faster than the pass
    % lasts, over one turn (as the 5 s sequence of the Sentinel-1B figures)
    span = t(end);
    if abs(stats.values.rate_about_H_deg_s) > 0
        span = min(span, 7/8*360/abs(stats.values.rate_about_H_deg_s));
    end
    t0 = max(0, min(t(end) - span, t(end)/2 - span/2));
    [~, k8] = min(abs(t - (t0 + linspace(0, span, 8))), [], 1);
    k8 = unique(k8);
    dt_tiles = t(k8(min(2, numel(k8)))) - t(k8(1));
    f = sprintf('%s_A_inertial_view.png', opts.prefix);
    draw_sequence(fullfile(opts.out_dir, f), 'inertial', t, R, W, Hm, k8, stats, opts);
    figs(end+1) = struct('file', f, 'title', 'Attitude sequence, fixed inertial view (H vertical)', 'caption', sprintf([ ...
        'Attitude every %.0f s over the pass in a fixed inertial view with the mean angular momentum H vertical. White arrow: H; ', ...
        'orange arrow: instantaneous rotation axis omega; red, green and blue arrows: body axes X, Y, Z (+Z = payload boresight); ', ...
        'white arc: sense of rotation about H.'], dt_tiles));
    f = sprintf('%s_B_view_along_H.png', opts.prefix);
    draw_sequence(fullfile(opts.out_dir, f), 'alongH', t, R, W, Hm, k8, stats, opts);
    figs(end+1) = struct('file', f, 'title', 'Same sequence seen along H', 'caption', ...
        ['Same sequence seen along H (H and omega point towards the reader): the rotation about H appears in the image plane. ', ...
        'Orange curve: path of the tip of omega during the pass.']);
    if ~isempty(opts.orbit_rv)
        f = sprintf('%s_C_H_orbital_plane.png', opts.prefix);
        draw_orbit_figure(fullfile(opts.out_dir, f), ts, H, W, Hm, stats, opts);
        figs(end+1) = struct('file', f, 'title', 'H and omega with respect to the orbit', 'caption', ...
            ['Angular momentum H and instantaneous rotation axis omega with respect to the orbit at the middle of the pass ', ...
            '(inertial view, END-001 orbit): Earth with land mask lit by the Sun, rotation axis, equator, orbital plane, velocity, ', ...
            'H, omega and sense of rotation; zoom on H and omega with respect to the orbital plane. Orbit radius not to scale.']);
    end
    f = sprintf('%s_D_parameters.png', opts.prefix);
    draw_parameters(fullfile(opts.out_dir, f), t, ts, q, R, w);
    figs(end+1) = struct('file', f, 'title', 'Attitude parameters from the AEM', 'caption', ...
        ['Content of the AEM over the pass: quaternion (J2000 to body, scalar last), the same attitude as ZYX Euler angles, ', ...
        'angular velocity in the body frame.']);

    for k = 1:numel(figs)                                      % Greek letter in the texts for the frontend
        figs(k).title = strrep(figs(k).title, 'omega', char(969));
        figs(k).caption = strrep(figs(k).caption, 'omega', char(969));
    end
    info.figures = figs;
    info.rotational_state = stats.rows;
    info.values = stats.values;
    js = struct('aem', aemFile, 'title', opts.title, 'rows', stats.rows, 'values', stats.values);
    fid = fopen(fullfile(opts.out_dir, sprintf('%s_rotational_state.json', opts.prefix)), 'w');
    if fid >= 0
        fprintf(fid, '%s', jsonencode(js, 'PrettyPrint', true));
        fclose(fid);
    end
end

%% =========================================================================
function opts = defaults(opts)
    d = struct('out_dir', pwd, 'prefix', 'aem', 'title', 'Attitude', 'I', eye(3), 'dims', [0.1 0.1 0.34], ...
        'mode', '', 'orbit_rv', [], 'gmst', [], 'site', [], 'site_role', 'site', 'frame_rot', []);
    fn = fieldnames(d);
    for k = 1:numel(fn)
        if ~isfield(opts, fn{k}) || isempty(opts.(fn{k}))
            opts.(fn{k}) = d.(fn{k});
        end
    end
end

function [ts, q, w] = read_aem(file)
    txt = fileread(file);
    blocks = regexp(txt, '<quaternionAngVel>(.*?)</quaternionAngVel>', 'tokens');
    if isempty(blocks)
        error('STAR:AEM:Type', 'No QUATERNION/ANGVEL states in %s', file);
    end
    body = strjoin(cellfun(@(c) c{1}, blocks, 'UniformOutput', false), newline);
    num = @(name) str2double(string(cellfun(@(c) c{1}, regexp(body, ['<' name '>\s*([^<\s]+)\s*</' name '>'], 'tokens'), 'UniformOutput', false)))';
    ep = string(cellfun(@(c) c{1}, regexp(body, '<EPOCH>\s*([^<\s]+)\s*</EPOCH>', 'tokens'), 'UniformOutput', false))';
    ep = replace(erase(ep, "Z"), "T", " ");
    ts = NaT(numel(ep), 1);
    frac = contains(ep, ".");
    if any(~frac), ts(~frac) = datetime(ep(~frac), 'InputFormat', 'yyyy-MM-dd HH:mm:ss'); end
    if any(frac)
        e2 = ep(frac);
        ndig = strlength(extractAfter(e2(1), "."));
        ts(frac) = datetime(e2, 'InputFormat', ['yyyy-MM-dd HH:mm:ss.' repmat('S', 1, ndig)]);
    end
    q = [num('Q1'), num('Q2'), num('Q3'), num('QC')];
    q = q./vecnorm(q, 2, 2);
    s = sign(sum(q(2:end, :).*q(1:end-1, :), 2)); s(s == 0) = 1;
    q = q.*cumprod([1; s]);
    w = [num('ANGVEL_X'), num('ANGVEL_Y'), num('ANGVEL_Z')];
end

function A = qdcm(q)
    q = q/norm(q); x = q(1); y = q(2); z = q(3); w = q(4);
    A = [1-2*(y^2+z^2) 2*(x*y-z*w) 2*(x*z+y*w); 2*(x*y+z*w) 1-2*(x^2+z^2) 2*(y*z-x*w); 2*(x*z-y*w) 2*(y*z+x*w) 1-2*(x^2+y^2)];
end

function Y = rot_rows(R, X)
    Y = zeros(size(X));
    for i = 1:size(X, 1), Y(i, :) = (R(:, :, i)*X(i, :)')'; end
end

function a = ang(u, v)
    a = atan2d(vecnorm(cross(u, v, 2), 2, 2), sum(u.*v, 2));
end

%% =========================================================================
%  ROTATIONAL STATE (Table 9 of the proposal)
%  =========================================================================
function st = rotational_state(t, ts, R, w, W, H, Hb, Hm, opts)
    n = numel(t);
    wd = rad2deg(vecnorm(w, 2, 2));
    Hmag = vecnorm(H, 2, 2);
    T = 0.5*sum(w.*Hb, 2);
    Hhat = H./max(Hmag, eps);
    rate_H = rad2deg(sum(W.*Hhat, 2));                       % rotation rate about H
    turned = trapz(t, rate_H);
    mean_rate = mean(rate_H);
    % body axis closest to H
    names = {'+X', '+Y', '+Z', '-X', '-Y', '-Z'};
    E = [eye(3); -eye(3)];
    meanang = zeros(6, 1); angs = zeros(n, 6);
    for j = 1:6
        axj = rot_rows(R, repmat(E(j, :), n, 1));
        angs(:, j) = ang(axj, Hhat);
        meanang(j) = mean(angs(:, j));
    end
    [~, jb] = min(meanang);
    Iv = eig((opts.I + opts.I')/2);
    Id = diag(opts.I);
    ax_i = mod(jb - 1, 3) + 1;
    tolI = 1e-6*max(Id);
    if abs(Id(ax_i) - max(Id)) <= tolI
        inertia_txt = 'maximum';
    elseif abs(Id(ax_i) - min(Id)) <= tolI
        inertia_txt = 'minimum';
    else
        inertia_txt = 'intermediate';
    end
    if isscalar(uniquetol(Id, 1e-6))
        inertia_txt = 'equal principal moments of inertia';
    elseif numel(uniquetol(Id, 1e-6)) == 2
        inertia_txt = [inertia_txt ' inertia; axisymmetric body'];
    else
        inertia_txt = [inertia_txt ' inertia'];
    end
    nut = angs(:, jb);
    nut_axis = names{jb};
    if numel(uniquetol(Id, 1e-6)) == 2                     % axisymmetric: nutation of the symmetry axis
        [~, js] = max(abs(Id - median(Id)));
        if meanang(js) <= meanang(js + 3), jn = js; else, jn = js + 3; end
        nut = angs(:, jn);
        nut_axis = ['symmetry axis ' names{jn}];
    end
    w_H = ang(W, Hhat);
    Ieff = mean(Hmag.^2./max(2*T, eps));
    Is = sort(Iv);
    Hdrift = max(ang(H, repmat(Hm, n, 1)));
    ra = mod(atan2d(Hm(2), Hm(1)), 360); de = asind(Hm(3));

    rows = struct('quantity', {}, 'value', {});
    add = @(qq, vv) struct('quantity', qq, 'value', vv);
    rows(end+1) = add('Epoch of the first state', [char(string(ts(1), 'yyyy-MM-dd HH:mm:ss.SSS')) ' UTC']);
    rows(end+1) = add('Duration of the pass, number of states', sprintf('%.1f s, %d states', t(end), n));
    if ~isempty(opts.mode), rows(end+1) = add('Attitude (STAR END-003)', sprintf('%s mode', strrep(opts.mode, '_', ' '))); end
    rows(end+1) = add(['Angular velocity magnitude |' char(969) '|'], sprintf('%s - %s deg/s (mean %s deg/s)', g3(min(wd)), g3(max(wd)), g3(mean(wd))));
    if abs(mean_rate) > 0
        rows(end+1) = add('Rotation about H', sprintf('%s deg/s, period %s (%.0f%s during the pass)', g3(mean_rate), ...
            dur_txt(360/abs(mean_rate)), abs(turned), char(176)));
    end
    if max(Hmag) > 0
        rows(end+1) = add('Angular momentum H, direction in J2000', sprintf('right ascension %.2f%s, declination %+.2f%s (moves by up to %.2f%s during the pass)', ...
            ra, char(176), de, char(176), Hdrift, char(176)));
        rows(end+1) = add('Angular momentum H, magnitude', sprintf('%s N m s', g3(mean(Hmag))));
        rows(end+1) = add('Rotational kinetic energy T', sprintf('%s J', g3(mean(T))));
        if strncmp(inertia_txt, 'equal', 5), axis_txt = inertia_txt; else, axis_txt = ['axis of ' inertia_txt]; end
    rows(end+1) = add('Body axis closest to H', sprintf('%s (%s)', names{jb}, axis_txt));
        [per, osc] = oscillation_period(t, nut);
        if osc
            rows(end+1) = add(sprintf('Nutation angle (%s to H)', nut_axis), sprintf('%.1f%s - %.1f%s, period %s', min(nut), char(176), max(nut), char(176), dur_txt(per)));
        else
            rows(end+1) = add(sprintf('Nutation angle (%s to H)', nut_axis), sprintf('%.2f%s - %.2f%s', min(nut), char(176), max(nut), char(176)));
        end
        rows(end+1) = add(['Angle between ' char(969) ' and H'], sprintf('%.2f%s - %.2f%s', min(w_H), char(176), max(w_H), char(176)));
        rows(end+1) = add(['H' char(178) '/2T and principal moments of inertia'], sprintf(['%s kg m' char(178) ' (principal: %s, %s, %s kg m' char(178) '): %s'], g3(Ieff), ...
            g3(Is(1)), g3(Is(2)), g3(Is(3)), spin_text(Ieff, Is)));
    end
    vals = struct('mean_rate_deg_s', mean(wd), 'min_rate_deg_s', min(wd), 'max_rate_deg_s', max(wd), ...
        'rate_about_H_deg_s', mean_rate, 'turned_deg', turned, 'H_ra_deg', ra, 'H_dec_deg', de, 'H_mag_Nms', mean(Hmag), ...
        'H_drift_deg', Hdrift, 'T_J', mean(T), 'closest_axis', names{jb}, 'nutation_min_deg', min(nut), 'nutation_max_deg', max(nut), ...
        'omega_H_min_deg', min(w_H), 'omega_H_max_deg', max(w_H), 'H2_over_2T_kgm2', Ieff);
    % H with respect to the orbit at mid pass
    if ~isempty(opts.orbit_rv)
        km = round((n + 1)/2);
        [r, v] = opts.orbit_rv(ts(km));
        rh = r/norm(r); nh = cross(r, v)/norm(cross(r, v)); vh = cross(nh, rh);
        hh = Hhat(km, :); wh = W(km, :)/max(norm(W(km, :)), eps);
        rows(end+1) = add('H with respect to the orbit (middle of the pass)', sprintf('%.0f%s from radial, %.0f%s from velocity, %.0f%s from the orbit normal (%.0f%s from the orbital plane)', ...
            ang(hh, rh), char(176), ang(hh, vh), char(176), ang(hh, nh), char(176), asind(abs(hh*nh')), char(176)));
        rows(end+1) = add([char(969) ' with respect to the orbit (middle of the pass)'], sprintf('%.0f%s from radial, %.0f%s from velocity, %.0f%s from the orbit normal (%.0f%s from the orbital plane)', ...
            ang(wh, rh), char(176), ang(wh, vh), char(176), ang(wh, nh), char(176), asind(abs(wh*nh')), char(176)));
        vals.H_from_radial_deg = ang(hh, rh); vals.H_from_velocity_deg = ang(hh, vh); vals.H_from_normal_deg = ang(hh, nh);
        vals.omega_from_radial_deg = ang(wh, rh); vals.omega_from_velocity_deg = ang(wh, vh); vals.omega_from_normal_deg = ang(wh, nh);
    end
    st.rows = rows;
    st.values = vals;
    st.sense = sign(mean_rate + (mean_rate == 0));
    st.closest_axis = names{jb};
end

function s = g3(x)
    if x == 0
        s = '0';
    elseif abs(x) >= 0.01 && abs(x) < 1e5
        s = sprintf('%.3g', x);
        if abs(x) >= 100, s = sprintf('%.1f', x); end
    else
        s = sprintf('%.3g', x);
    end
end

function s = dur_txt(sec)
    if sec < 120
        s = sprintf('%.1f s', sec);
    elseif sec < 7200
        s = sprintf('%.1f min', sec/60);
    else
        s = sprintf('%.2f h', sec/3600);
    end
end

function [per, osc] = oscillation_period(t, x)
    per = NaN; osc = false;
    if numel(x) < 5 || max(x) - min(x) < 0.5, return; end
    y = x - mean(x);
    zc = find(y(1:end-1).*y(2:end) < 0);
    if numel(zc) >= 3
        per = 2*mean(diff(t(zc)));
        osc = true;
    end
end

function s = spin_text(Ieff, Is)
    tol = 0.01*Is(3);
    if abs(Ieff - Is(3)) < tol
        s = 'pure spin about the axis of maximum inertia';
    elseif abs(Ieff - Is(1)) < tol
        s = 'pure spin about the axis of minimum inertia';
    elseif Ieff > Is(2)
        s = 'nutating rotation about the axis of maximum inertia (stable)';
    else
        s = 'nutating rotation about the axis of minimum inertia (unstable with energy dissipation)';
    end
end

%% =========================================================================
%  FIGURES A / B: attitude sequence
%  =========================================================================
function draw_sequence(file, kind, t, R, W, Hm, k8, st, opts)
    bg = [0.13 0.15 0.19];
    fig = new_fig([40 40 1900 1120], bg);
    tl = tiledlayout(fig, 2, 4, 'TileSpacing', 'tight', 'Padding', 'compact');
    tl.OuterPosition = [0 0.075 1 0.925];
    [e1, e2] = perp_basis(Hm);
    if strcmp(kind, 'inertial')
        p = e1;
        dview = cosd(16)*p + sind(16)*Hm;
        up = Hm;
    else
        dview = Hm;
        up = e1;
    end
    Wn = W./max(vecnorm(W, 2, 2), eps);
    hasW = max(vecnorm(W, 2, 2)) > 0;
    LH = 1.55; LW = 1.38; LA = 1.12;
    tips = LW*Wn;
    col = struct('H', [0.93 0.95 0.98], 'w', [0.98 0.55 0.22], 'X', [0.93 0.33 0.30], 'Y', [0.35 0.80 0.40], 'Z', [0.40 0.60 0.98]);
    for k = k8(:)'
        ax = nexttile(tl);
        hold(ax, 'on'); axis(ax, 'equal'); axis(ax, 'off');
        ax.Color = bg;
        Rk = R(:, :, k);
        draw_cubesat(ax, Rk, opts.dims);
        % body axes
        B = {'X', 'Y', 'Z'};
        for j = 1:3
            a = Rk(:, j)';
            arrow3(ax, [0 0 0], LA*a, col.(B{j}), 0.022);
            text(ax, 1.08*LA*a(1), 1.08*LA*a(2), 1.08*LA*a(3), B{j}, 'Color', col.(B{j}), 'FontWeight', 'bold', 'FontSize', 15, ...
                'HorizontalAlignment', 'center');
        end
        % angular momentum and rotation axis
        arrow3(ax, [0 0 0], LH*Hm, col.H, 0.024);
        text(ax, 1.1*LH*Hm(1) + 0.08*up(1), 1.1*LH*Hm(2) + 0.08*up(2), 1.1*LH*Hm(3) + 0.08*up(3), 'H', 'Color', col.H, ...
            'FontWeight', 'bold', 'FontSize', 15, 'HorizontalAlignment', 'left');
        if hasW
            arrow3(ax, [0 0 0], LW*Wn(k, :), col.w, 0.02);
            wl = 1.1*LW*Wn(k, :) - 0.12*e2;
            text(ax, wl(1), wl(2), wl(3), '\omega', 'Color', col.w, 'FontWeight', 'bold', 'FontSize', 16, 'HorizontalAlignment', 'right');
            plot3(ax, tips(:, 1), tips(:, 2), tips(:, 3), '-', 'Color', [col.w 0.85], 'LineWidth', 1.6);
        end
        % sense of rotation about H
        draw_arc(ax, (strcmp(kind, 'inertial')*1.0 + ~strcmp(kind, 'inertial')*0.2)*Hm, Hm, ...
            0.34*strcmp(kind, 'inertial') + 1.12*~strcmp(kind, 'inertial'), st.sense, [0.95 0.95 0.97], 2.2);
        lim = 1.75;
        xlim(ax, [-lim lim]); ylim(ax, [-lim lim]); zlim(ax, [-lim lim]);
        camproj(ax, 'orthographic');
        campos(ax, 20*dview); camtarget(ax, [0 0 0]); camup(ax, up); camva(ax, 9.6);
        light(ax, 'Position', 6*dview + 4*up + 3*cross(up, dview), 'Style', 'infinite');
        light(ax, 'Position', -3*dview + 2*up, 'Style', 'infinite', 'Color', [0.35 0.35 0.4]);
        lighting(ax, 'gouraud');
        text(ax, 0.03, 0.97, sprintf('t = %.0f s', t(k)), 'Units', 'normalized', 'Color', 'w', 'FontSize', 17, 'FontWeight', 'bold', ...
            'VerticalAlignment', 'top');
    end
    if strcmp(kind, 'inertial')
        note = 'White arc: sense of rotation about H. Orange curve: path of the tip of \omega during the pass. Fixed inertial view, mean H vertical.';
    else
        note = 'View along H (H and \omega point towards the reader). White arc: sense of rotation. Orange curve: path of the tip of \omega.';
    end
    legend_strip(fig, bg, {'angular momentum H', 'rotation axis \omega', 'X body', 'Y body', 'Z body (payload boresight)'}, ...
        [col.H; col.w; col.X; col.Y; col.Z], note, opts.title);
    save_fig(fig, file);
end

function legend_strip(fig, bg, labels, colors, note, ttl)
    ax = axes(fig, 'Position', [0 0 1 0.075], 'Color', bg, 'XColor', 'none', 'YColor', 'none');
    hold(ax, 'on'); xlim(ax, [0 1]); ylim(ax, [0 1]);
    x = 0.012;
    for i = 1:numel(labels)
        patch(ax, x + [0 0.018 0.018 0], [0.62 0.62 0.8 0.8], colors(i, :), 'EdgeColor', [0.6 0.6 0.6]);
        h = text(ax, x + 0.024, 0.71, labels{i}, 'Color', [0.93 0.93 0.95], 'FontSize', 14, 'VerticalAlignment', 'middle');
        e = h.Extent;
        x = x + 0.024 + e(3) + 0.025;
    end
    text(ax, 0.012, 0.25, note, 'Color', [0.72 0.74 0.78], 'FontSize', 12.5, 'VerticalAlignment', 'middle');
    text(ax, 0.988, 0.25, ttl, 'Color', [0.72 0.74 0.78], 'FontSize', 12.5, 'VerticalAlignment', 'middle', ...
        'HorizontalAlignment', 'right', 'Interpreter', 'none');
end

function draw_cubesat(ax, R, dims)
    % CubeSat with the sides of the equivalent box: aluminium frame and rails,
    % solar cells on the four long faces, payload lens on +Z (boresight).
    h = 0.6*dims/max(dims);
    metal = [0.74 0.75 0.78]; cells = [0.12 0.20 0.46]; dark = [0.16 0.17 0.19];
    rail = 0.075*min(h(1:2));
    patch_box(ax, R, [0 0 0], h - [rail rail 0]*0.4, metal);
    for sx = [-1 1]
        for sy = [-1 1]
            patch_box(ax, R, [sx*(h(1) - rail) sy*(h(2) - rail) 0], [rail rail h(3)*1.02], [0.55 0.56 0.6]);
        end
    end
    th = 0.004;
    patch_box(ax, R, [h(1) + th 0 0], [th 0.82*h(2) 0.92*h(3)], cells);
    patch_box(ax, R, [-h(1) - th 0 0], [th 0.82*h(2) 0.92*h(3)], cells);
    patch_box(ax, R, [0 h(2) + th 0], [0.82*h(1) th 0.92*h(3)], cells);
    patch_box(ax, R, [0 -h(2) - th 0], [0.82*h(1) th 0.92*h(3)], cells);
    % lens on +Z and a dark patch antenna on -Z
    rl = 0.55*min(h(1:2));
    [X, Y, Z] = cylinder([rl rl], 28); Z = h(3) + 0.12*h(3)*Z;
    surf_body(ax, R, X, Y, Z, dark);
    [X, Y, Z] = cylinder([rl 0.62*rl], 28); Z = h(3)*1.12 + 0.002 + 0*Z;
    surf_body(ax, R, X, Y, Z, [0.05 0.06 0.1]);
    patch_box(ax, R, [0 0 -h(3) - th], [0.5*h(1) 0.5*h(2) th], [0.62 0.48 0.22]);
end

function patch_box(ax, R, c, hs, colr)
    s = [-1 -1 -1; 1 -1 -1; 1 1 -1; -1 1 -1; -1 -1 1; 1 -1 1; 1 1 1; -1 1 1];
    V = (c + s.*hs)*R';
    F = [1 2 3 4; 5 6 7 8; 1 2 6 5; 2 3 7 6; 3 4 8 7; 4 1 5 8];
    patch(ax, 'Vertices', V, 'Faces', F, 'FaceColor', colr, 'EdgeColor', 'none', 'FaceLighting', 'flat', ...
        'AmbientStrength', 0.45, 'DiffuseStrength', 0.75, 'SpecularStrength', 0.25);
end

function surf_body(ax, R, X, Y, Z, colr)
    P = [X(:) Y(:) Z(:)]*R';
    surf(ax, reshape(P(:, 1), size(X)), reshape(P(:, 2), size(X)), reshape(P(:, 3), size(X)), 'FaceColor', colr, ...
        'EdgeColor', 'none', 'FaceLighting', 'gouraud', 'AmbientStrength', 0.45);
end

function arrow3(ax, p0, vec, colr, rad)
    L = norm(vec);
    if L < 1e-9, return; end
    u = vec/L;
    hl = min(0.3*L, 6*rad); sl = L - hl;
    B = basis_from_z(u);
    [X, Y, Z] = cylinder([rad rad], 18); Z = Z*sl;
    surf_local(ax, X, Y, Z, B, p0, colr);
    [X, Y, Z] = cylinder([2.5*rad 0], 18); Z = Z*hl + sl;
    surf_local(ax, X, Y, Z, B, p0, colr);
end

function surf_local(ax, X, Y, Z, B, p0, colr)
    P = [X(:) Y(:) Z(:)]*B' + p0;
    surf(ax, reshape(P(:, 1), size(X)), reshape(P(:, 2), size(X)), reshape(P(:, 3), size(X)), 'FaceColor', colr, ...
        'EdgeColor', 'none', 'FaceLighting', 'gouraud', 'AmbientStrength', 0.6);
end

function B = basis_from_z(u)
    a = [1 0 0];
    if abs(u(1)) > 0.9, a = [0 1 0]; end
    e1 = cross(u, a); e1 = e1/norm(e1);
    e2 = cross(u, e1);
    B = [e1' e2' u(:)];
end

function [e1, e2] = perp_basis(n)
    % e1, e2 orthonormal, perpendicular to n, with e1 x e2 = n.
    n = n/norm(n);
    a = [0 0 1];
    if abs(n*a') > 0.9, a = [1 0 0]; end
    e1 = cross(n, a); e1 = e1/norm(e1);
    e2 = cross(n, e1);
end

function draw_arc(ax, c, n, rad, sense, colr, lw)
    % Arc of 300 deg about n, counterclockwise seen from the tip of n when sense > 0.
    [e1, e2] = perp_basis(n);
    phi = sense*linspace(0, 5*pi/3, 90)';
    P = c + rad*(cos(phi)*e1 + sin(phi)*e2);
    plot3(ax, P(:, 1), P(:, 2), P(:, 3), 'Color', colr, 'LineWidth', lw);
    tg = sense*(-sin(phi(end))*e1 + cos(phi(end))*e2);
    arrow3(ax, P(end, :) - 0.06*tg, 0.14*tg, colr, 0.016);
end

%% =========================================================================
%  FIGURE C: H with respect to the orbit
%  =========================================================================
function draw_orbit_figure(file, ts, H, W, Hm, st, opts)
    n = numel(ts);
    km = round((n + 1)/2);
    [r, v] = opts.orbit_rv(ts(km));
    rh = r/norm(r); nh = cross(r, v)/norm(cross(r, v)); vh = cross(nh, rh);
    hh = H(km, :)/max(norm(H(km, :)), eps);
    if norm(H(km, :)) == 0, hh = Hm; end
    wn = norm(W(km, :));
    wh = W(km, :)/max(wn, eps);
    fig = new_fig([40 40 1900 960], [1 1 1]);

    % ---- left: inertial view (Earth north up, satellite near the limb, orbital plane seen at a grazing angle)
    ax = axes(fig, 'Position', [0.0 0.07 0.56 0.86]);
    hold(ax, 'on'); axis(ax, 'equal'); axis(ax, 'off');
    Ro = 1.9;
    th0 = 0;
    if ~isempty(opts.gmst), th0 = opts.gmst(ts(km)); end
    % side view with north up: of the four sign choices, the most horizontal
    best = inf;
    for s1 = [1 -1]
        for s2 = [-1 1]
            dc = 0.55*rh + 0.35*s1*nh + 0.75*s2*vh; dc = dc/norm(dc);
            if abs(dc(3)) < best, best = abs(dc(3)); d = dc; end
        end
    end
    if abs(d(3)) > 0.5                                % polar view: tilt towards the horizon
        d(3) = 0.5*sign(d(3)); d(1:2) = d(1:2)/norm(d(1:2))*sqrt(1 - 0.25);
    end
    scr.up = [0 0 1] - d(3)*d; scr.up = scr.up/norm(scr.up);
    scr.right = cross(-d, scr.up);
    draw_earth(ax, th0);
    sunv = sun_dir(ts(km));
    navy = [0.10 0.22 0.42]; green = [0.18 0.55 0.25]; orange = [0.88 0.42 0.08]; grey = [0.38 0.38 0.40];
    ph = linspace(0, 2*pi, 240)';
    % equatorial plane, equator, Earth axis
    fill3(ax, Ro*1.12*cos(ph), Ro*1.12*sin(ph), 0*ph, [0.85 0.85 0.85], 'FaceAlpha', 0.07, 'EdgeColor', [0.6 0.6 0.6], 'LineStyle', '--');
    plot3(ax, 1.004*cos(ph), 1.004*sin(ph), 0*ph, 'Color', [1 1 1], 'LineWidth', 1.6);
    e = [scr.right(1) scr.right(2) 0]; e = e/max(norm(e), eps);
    label3(ax, Ro*1.12*e, e, 'Equatorial plane', [0.45 0.45 0.45], 12, 'normal', scr);
    arrow3(ax, [0 0 -1.5], [0 0 3.2], [0.25 0.25 0.28], 0.012);
    label3(ax, [0 0 -1.5], [0 0 -1], 'Earth rotation axis (north up)', [0.2 0.2 0.22], 12, 'normal', scr);
    % orbital plane and orbit (radius not to scale)
    P = Ro*(cos(ph)*rh + sin(ph)*vh);
    fill3(ax, P(:, 1), P(:, 2), P(:, 3), [0.55 0.72 0.92], 'FaceAlpha', 0.16, 'EdgeColor', 'none');
    plot3(ax, P(:, 1), P(:, 2), P(:, 3), 'Color', navy, 'LineWidth', 2.2);
    % label on the part of the orbit farthest from the Earth on the screen, away from the satellite
    phs = (100:5:260)';
    Q = Ro*(cosd(phs)*rh + sind(phs)*vh);
    [~, iq] = max(hypot(Q*scr.right', Q*scr.up'));
    label3(ax, Q(iq, :), Q(iq, :), 'Orbit (orbital plane shaded)', navy, 13, 'normal', scr);
    % orbit normal from the centre
    arrow3(ax, [0 0 0], 2.3*nh, grey, 0.012);
    label3(ax, 2.3*nh, nh, 'orbit normal', grey, 12, 'normal', scr);
    % satellite and its vectors
    s0 = Ro*rh;
    plot3(ax, [0 s0(1)], [0 s0(2)], [0 s0(3)], '--', 'Color', [0.95 0.95 0.95], 'LineWidth', 1.2);
    plot3(ax, s0(1), s0(2), s0(3), 'd', 'MarkerSize', 11, 'MarkerFaceColor', [0.98 0.62 0.18], 'MarkerEdgeColor', [0.4 0.25 0.05]);
    arrow3(ax, s0, 0.8*vh, green, 0.02);
    label3(ax, s0 + 0.8*vh, vh, 'Velocity v', green, 13, 'bold', scr);
    arrow3(ax, s0, 0.85*hh, navy, 0.022);
    parallel = ~(wn > 0 && ang(hh, wh) > 1);
    label3(ax, s0 + 0.85*hh, hh, 'Angular momentum H', navy, 13, 'bold', scr);
    if ~parallel
        arrow3(ax, s0, 0.7*wh, orange, 0.018);
        label3(ax, s0 + 0.7*wh, wh, ['Instantaneous rotation axis ' char(969)], orange, 12, 'bold', scr, ang(hh, wh) < 20);
    end
    draw_arc(ax, s0 + 0.48*hh, hh, 0.14, st.sense, [0.8 0.33 0.05], 2.2);
    % ground point
    if ~isempty(opts.site) && isstruct(opts.site)
        [pg, ~] = geodetic(opts.site.lat, opts.site.lon, opts.site.alt);
        pg = rot_z(pg, th0)/6378137;
        if ~isempty(opts.frame_rot), pg = pg*opts.frame_rot'; end
        if pg*d' > 0                                  % on the visible hemisphere
            plot3(ax, pg(1)*1.01, pg(2)*1.01, pg(3)*1.01, 'o', 'MarkerSize', 8, 'MarkerFaceColor', [0.85 0.1 0.1], 'MarkerEdgeColor', 'w');
            label3(ax, pg*1.02, pg, opts.site.name, [0.85 0.1 0.1], 12, 'bold', scr, true);
        end
    end
    camproj(ax, 'orthographic'); campos(ax, 30*d); camtarget(ax, [0 0 0]); camup(ax, [0 0 1]); camva(ax, 11.8);
    light(ax, 'Position', 10*sunv, 'Style', 'infinite');
    lighting(ax, 'gouraud');
    annotation(fig, 'textbox', [0.0 0.94 0.56 0.05], 'String', ['H and ' char(969) ' with respect to the orbit (inertial view, middle of the pass)'], ...
        'EdgeColor', 'none', 'FontSize', 14, 'FontWeight', 'bold', 'Color', [0.15 0.15 0.15], 'HorizontalAlignment', 'center', 'Interpreter', 'none');
    rate_txt = '';
    if isfield(st.values, 'rate_about_H_deg_s')
        rate_txt = sprintf('  |  rotation about H %s deg/s', g3(abs(st.values.rate_about_H_deg_s)));
    end
    if parallel && wn > 0
        rate_txt = [rate_txt '  |  ' char(969) ' parallel to H'];
    end
    annotation(fig, 'textbox', [0.01 0.0 0.75 0.04], 'VerticalAlignment', 'bottom', 'String', sprintf('%s  |  %s UTC%s  |  orbit radius not to scale', opts.title, ...
        char(string(ts(km), 'yyyy-MM-dd HH:mm:ss')), rate_txt), 'EdgeColor', 'none', 'FontSize', 11, 'Color', [0.35 0.35 0.35], 'Interpreter', 'none');

    % ---- right: zoom in the orbital frame (x = velocity, y = radial, z = normal)
    az = axes(fig, 'Position', [0.58 0.2 0.40 0.72]);
    hold(az, 'on'); axis(az, 'equal'); axis(az, 'off');
    loc = @(u) [u*vh', u*rh', u*nh'];
    Hl = loc(hh); Wl = loc(wh);
    fill3(az, [-1.1 1.1 1.1 -1.1], [-1.1 -1.1 1.1 1.1], [0 0 0 0], [0.75 0.85 0.97], 'FaceAlpha', 0.45, ...
        'EdgeColor', [0.3 0.45 0.75], 'LineStyle', '--');
    text(az, -1.05, -1.0, 0, 'orbital plane', 'FontSize', 12, 'Color', [0.2 0.35 0.65]);
    arrow3(az, [0 0 0], [0 0 1.15], [0.45 0.45 0.48], 0.014);
    text(az, 0, 0, 1.24, 'orbit normal', 'FontSize', 12, 'Color', [0.35 0.35 0.38], 'HorizontalAlignment', 'center');
    arrow3(az, [0 0 0], [-1.05 0 0], [0.18 0.55 0.25], 0.014);
    text(az, -1.18, 0, 0, 'velocity', 'FontSize', 12, 'Color', [0.18 0.55 0.25], 'HorizontalAlignment', 'right');
    arrow3(az, [0 0 0], [0 1.05 0], [0.45 0.45 0.48], 0.014);
    text(az, 0.05, 1.16, 0, 'radial (Earth \rightarrow satellite)', 'FontSize', 12, 'Color', [0.35 0.35 0.38]);
    % velocity is +x: draw it on the left as in the proposal (x axis reversed)
    Hd = [-Hl(1) Hl(2) Hl(3)]; Wd = [-Wl(1) Wl(2) Wl(3)];
    arrow3(az, [0 0 0], 1.0*Hd, [0.10 0.22 0.42], 0.022);
    plot3(az, [Hd(1) Hd(1)], [Hd(2) Hd(2)], [0 Hd(3)], ':', 'Color', [0.10 0.22 0.42], 'LineWidth', 1.4);
    plot3(az, [0 Hd(1)], [0 Hd(2)], [0 0], ':', 'Color', [0.10 0.22 0.42], 'LineWidth', 1.4);
    text(az, 1.08*Hd(1), 1.08*Hd(2), 1.08*Hd(3) + 0.04, 'H  ', 'FontSize', 18, 'FontWeight', 'bold', 'Color', [0.10 0.22 0.42], 'HorizontalAlignment', 'right');
    if wn > 0 && ang(hh, wh) > 1
        arrow3(az, [0 0 0], 0.9*Wd, [0.88 0.42 0.08], 0.018);
        plot3(az, [Wd(1) Wd(1)]*0.9, [Wd(2) Wd(2)]*0.9, [0 Wd(3)*0.9], ':', 'Color', [0.88 0.42 0.08], 'LineWidth', 1.3);
        text(az, 0.98*Wd(1), 0.98*Wd(2), 0.98*Wd(3) - 0.06, '  \omega', 'FontSize', 18, 'FontWeight', 'bold', 'Color', [0.88 0.42 0.08], 'HorizontalAlignment', 'left');
    end
    view(az, [-128 20]);
    camproj(az, 'orthographic');
    lighting(az, 'gouraud'); light(az, 'Position', [-1 -2 3], 'Style', 'infinite');
    annotation(fig, 'textbox', [0.58 0.94 0.40 0.05], 'String', ['Zoom: H and ' char(969) ' with respect to the orbital plane'], ...
        'EdgeColor', 'none', 'FontSize', 14, 'FontWeight', 'bold', 'Color', [0.15 0.15 0.15], 'HorizontalAlignment', 'center', 'Interpreter', 'none');
    v = st.values;
    l1 = sprintf('H:  %.0f%s from radial,  %.0f%s from velocity,  %.0f%s from normal', v.H_from_radial_deg, char(176), ...
        v.H_from_velocity_deg, char(176), v.H_from_normal_deg, char(176));
    l2 = sprintf('%s:  %.0f%s from radial,  %.0f%s from velocity,  %.0f%s from normal', char(969), v.omega_from_radial_deg, char(176), ...
        v.omega_from_velocity_deg, char(176), v.omega_from_normal_deg, char(176));
    annotation(fig, 'textbox', [0.58 0.10 0.40 0.05], 'String', l1, 'EdgeColor', 'none', 'FontSize', 13, 'FontWeight', 'bold', ...
        'Color', [0.10 0.22 0.42], 'HorizontalAlignment', 'center', 'Interpreter', 'none');
    if wn > 0
        annotation(fig, 'textbox', [0.58 0.05 0.40 0.05], 'String', l2, 'EdgeColor', 'none', 'FontSize', 13, 'FontWeight', 'bold', ...
            'Color', [0.88 0.42 0.08], 'HorizontalAlignment', 'center', 'Interpreter', 'none');
    end
    save_fig(fig, file);
end

function label3(ax, tip, dirv, txt, colr, fs, fw, scr, below)
    % Text just beyond an arrow tip, aligned away from the arrow on the screen
    % (below = true: under the tip, for a vector close to another labelled one).
    dirv = dirv/max(norm(dirv), eps);
    dx = dirv*scr.right'; dy = dirv*scr.up';
    if dx >= 0, ha = 'left'; else, ha = 'right'; end
    if abs(dy) > 2.5*abs(dx), ha = 'center'; end
    if dy >= 0, va = 'bottom'; else, va = 'top'; end
    if abs(dx) > 2.5*abs(dy), va = 'middle'; end
    if nargin > 8 && below, va = 'top'; tip = tip - 0.06*scr.up; end
    p = tip + 0.05*dirv;
    text(ax, p(1), p(2), p(3), txt, 'HorizontalAlignment', ha, 'VerticalAlignment', va, 'Color', colr, ...
        'FontSize', fs, 'FontWeight', fw, 'Interpreter', 'none');
end

function draw_earth(ax, th0)
    persistent img
    if isempty(img)
        try
            s = load('topo.mat', 'topo');
            land = s.topo > 0;
            sea = [0.15 0.35 0.66]; ground = [0.38 0.58 0.30];
            img = zeros([size(land) 3]);
            for c = 1:3
                img(:, :, c) = land*ground(c) + ~land*sea(c);
            end
            shade = min(1, 0.85 + 0.15*max(0, s.topo)/3000);
            img = img.*(land.*shade + ~land);
        catch
            img = repmat(reshape([0.2 0.4 0.7], 1, 1, 3), 180, 360);
        end
    end
    lat = linspace(-90, 90, 181)'; lon = linspace(0, 360, 361);
    X = cosd(lat)*cosd(lon + rad2deg(th0));
    Y = cosd(lat)*sind(lon + rad2deg(th0));
    Z = sind(lat)*ones(size(lon));
    surf(ax, X, Y, Z, 'CData', img, 'FaceColor', 'texturemap', 'EdgeColor', 'none', 'FaceLighting', 'gouraud', ...
        'AmbientStrength', 0.55, 'DiffuseStrength', 0.7, 'SpecularStrength', 0.05);
end

function s = sun_dir(ts)
    n = juliandate(ts) - 2451545.0;
    L = mod(280.460 + 0.9856474*n, 360);
    g = mod(357.528 + 0.9856003*n, 360);
    lam = L + 1.915*sind(g) + 0.020*sind(2*g);
    e = 23.439 - 0.0000004*n;
    s = [cosd(lam), sind(lam)*cosd(e), sind(lam)*sind(e)];
end

function [p, up] = geodetic(lat, lon, alt)
    a = 6378137.0; f = 1/298.257223563; e2 = f*(2 - f);
    N = a/sqrt(1 - e2*sin(lat)^2);
    p = [(N + alt)*cos(lat)*cos(lon), (N + alt)*cos(lat)*sin(lon), (N*(1 - e2) + alt)*sin(lat)];
    up = [cos(lat)*cos(lon), cos(lat)*sin(lon), sin(lat)];
end

function x = rot_z(x, th)
    x = [cos(th)*x(1) - sin(th)*x(2), sin(th)*x(1) + cos(th)*x(2), x(3)];
end

%% =========================================================================
%  FIGURE D: attitude parameters
%  =========================================================================
function draw_parameters(file, t, ts, q, R, w)
    n = numel(t);
    eul = zeros(n, 3);
    for i = 1:n
        C = R(:, :, i)';                              % J2000 -> body
        eul(i, :) = [atan2(C(1, 2), C(1, 1)), -asin(max(-1, min(1, C(1, 3)))), atan2(C(2, 3), C(3, 3))];
    end
    eul = rad2deg(unwrap(eul));
    wd = rad2deg(w);
    c = [0.16 0.47 0.82; 0.91 0.40 0.22; 0.10 0.64 0.48; 0.93 0.63 0.07];
    fig = new_fig([40 40 1300 1200], [1 1 1]);
    tl = tiledlayout(fig, 3, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
    ax = nexttile(tl); hold(ax, 'on');
    for j = 1:4, plot(ax, t, q(:, j), 'LineWidth', 2.2, 'Color', c(j, :)); end
    ylabel(ax, 'quaternion (J2000 \rightarrow body)'); ylim(ax, [-1.05 1.05]); style(ax);
    legend(ax, {'Q1', 'Q2', 'Q3', 'QC (scalar)'}, 'Orientation', 'horizontal', 'Location', 'northoutside', 'Box', 'off', 'FontSize', 12);
    ax = nexttile(tl); hold(ax, 'on');
    for j = 1:3, plot(ax, t, eul(:, j), 'LineWidth', 2.2, 'Color', c(j, :)); end
    ylabel(ax, 'Euler angles ZYX (deg)'); style(ax);
    legend(ax, {'angle 1 (about Z)', 'angle 2 (about Y)', 'angle 3 (about X)'}, 'Orientation', 'horizontal', 'Location', 'northoutside', 'Box', 'off', 'FontSize', 12);
    ax = nexttile(tl); hold(ax, 'on');
    for j = 1:3, plot(ax, t, wd(:, j), 'LineWidth', 2.2, 'Color', c(j, :)); end
    plot(ax, t, vecnorm(wd, 2, 2), '--', 'LineWidth', 2, 'Color', [0.3 0.3 0.3]);
    ylabel(ax, 'angular velocity, body frame (deg/s)'); style(ax);
    legend(ax, {'\omega_x', '\omega_y', '\omega_z', '|\omega|'}, 'Orientation', 'horizontal', 'Location', 'northoutside', 'Box', 'off', 'FontSize', 12);
    xlabel(ax, sprintf('time from %s UTC (s)', char(string(ts(1), 'yyyy-MM-dd HH:mm:ss.SSS'))));
    save_fig(fig, file);
end

function style(ax)
    grid(ax, 'on'); box(ax, 'off');
    ax.GridColor = [0.85 0.85 0.85]; ax.GridAlpha = 1; ax.FontSize = 12;
    ax.XColor = [0.35 0.35 0.35]; ax.YColor = [0.35 0.35 0.35];
    axis(ax, 'tight'); yl = ylim(ax); ylim(ax, yl + [-1 1]*0.06*max(diff(yl), 1e-6));
end

function fig = new_fig(pos, colr)
    % Light theme whatever the desktop theme (R2025a+), then the background colour.
    fig = figure('Visible', 'off', 'Position', pos);
    try
        fig.Theme = 'light';
    catch
    end
    fig.Color = colr;
end

function save_fig(fig, file)
    try
        drawnow;
        exportgraphics(fig, file, 'Resolution', 110, 'BackgroundColor', 'current');
    catch
        print(fig, file, '-dpng', '-r110');
    end
    close(fig);
end
