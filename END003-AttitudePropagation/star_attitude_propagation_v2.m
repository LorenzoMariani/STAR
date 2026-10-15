%% STAR END-003: ATTITUDE PROPAGATOR ======================================

% STAR_END003_ATTTITUDE_PROPAGATION()
% Load input from JSON file and execute attitude propagation.
% - Input:
% file_input: path + filename of the input json file
% path_output: folder with the simulation output (CSV and Graphs)
% - Output:
% CSV: CSV file for END-007 (Synthetic Data Generation)
% Graphs: Plots to control simulation results
% - Help:
% Attitude_mode available options: 
% 'dynamics'    -> Integrates attitude naturally subject to space disturbances
% 'nadir'       -> Imposes ideal Nadir Pointing attitude geometrically
% 'follow_site' -> Imposes Nadir, switches to Target Pointing during coverage


clear; clc; close all;
set(0, DefaultFigureVisible, off);

file_input = "C:\Users\s5oss\Desktop\software_s5lab\STAR\Input\input_attitude_propagator.json";
path_output = "C:\Users\s5oss\Desktop\software_s5lab\STAR\Output";

STAR_END003_ATTITUDE_PROPAGATION(file_input, path_output)


%% =======================================================================%
% == MAIN FUNCTION (API) =================================================%
%=========================================================================%
function STAR_END003_ATTITUDE_PROPAGATION(configFile, output_folder)
    output_plot = output_folder + "\results_attitude_propagator";
    if nargin < 2
        output_plot = 'simulation_outputs';
    end 
    % Create folder if not exists
    if ~exist(output_plot, 'dir')
        mkdir(output_plot);
    end
    out_dir = output_folder + "\output_attitude_propagation";
    if ~exist(out_dir, 'dir')
        mkdir(out_dir);
    end
    %% == LOAD INPUT FROM JSON ============================================
    if ~exist(configFile, 'file')
        error('File JSON not found: %s', configFile);
    end    
    cfg = jsondecode(fileread(configFile));    
    % SIMULATION DATETIME
    sim_start_date = datetime(cfg.sim_start_date, 'InputFormat', 'yyyy-MM-dd HH:mm:ss');
    sim_hours = cfg.sim_hours;    
    % SATELLITE
    sat.attitude_mode = cfg.sat.attitude_mode;
    q0 = cfg.sat.q0(:); 
    w0 = cfg.sat.w0(:);
    sat.m = cfg.sat.m;
    sat.A_ref = cfg.sat.A_ref;
    sat.Cr = cfg.sat.Cr;
    sat.Cd = cfg.sat.Cd;
    sat.r_cp = cfg.sat.r_cp(:);
    sat.I = diag([cfg.sat.Ix; cfg.sat.Iy; cfg.sat.Iz]);    
    % Flags
    env.flags = cfg.env.flags;
    env.Re = cfg.env.Re;   
    % SITE
    site_lat = deg2rad(cfg.target.site_lat_deg);
    site_lon = deg2rad(cfg.target.site_lon_deg);
    elev_threshold = cfg.target.elev_threshold;

    % SUN CONSTRAINT ON TARGET SITE
    sun_constraint_enabled = false;
    sun_constraint_mode = "any";
    sun_elev_threshold_deg = 0;
    
    if isfield(cfg.target, 'Sun_Constraint')
        sun_constraint_enabled = logical(cfg.target.Sun_Constraint);
    end
    
    if isfield(cfg.target, 'Sun_Constraint_Mode')
        sun_constraint_mode = lower(string(cfg.target.Sun_Constraint_Mode));
    end
    
    if isfield(cfg.target, 'Sun_Elevation_Threshold_Deg')
        sun_elev_threshold_deg = cfg.target.Sun_Elevation_Threshold_Deg;
    end
    
    if sun_constraint_enabled
        if ~(sun_constraint_mode == "day" || sun_constraint_mode == "night")
            error('Sun_Constraint_Mode must be either "day" or "night".');
        end
    end

    % COE
    rp = env.Re + cfg.orbit.alt_perigee_m;
    ra = env.Re + cfg.orbit.alt_apogee_m;
    coe.a = (rp + ra)/2;
    coe.e = (ra - rp)/(ra + rp);
    coe.i = deg2rad(cfg.orbit.inclination_deg);
    coe.RAAN = deg2rad(cfg.orbit.raan_deg);
    coe.omega = deg2rad(cfg.orbit.omega_deg);
    coe.nu = deg2rad(cfg.orbit.nu_deg);

    % == ENVIRONMENT
    env.mu = 3.986e14;
    env.J2 = 1.0826e-3;
    env.J3 = -2.5321e-6;
    env.we = 7.2921e-5;
    env.P_sun = 4.56e-6;
    % Magnetic Field Constants
    alt_limit_B = 600e3;        
    M_earth = 7.746e22;         
    mu0 = 4*pi*1e-7;
    lat_mag = deg2rad(80.5);    
    lon_mag = deg2rad(-72.6);
    % Atmospheric Constants
    alt_start_fade = 700e3;     
    alt_end_fade = 1000e3;      
    f107ave = 150; f107 = 150; ap = 15; 
    
    %% == START ===============================================================  
    fprintf('--- START SIMULATION (%s mode) ---\n', sat.attitude_mode);
    total_tic = tic;
    
    % == ORBITAL ELEMENTS
    [r0, v0] = coe2rv(coe, env.mu);
    tspan = [0 sim_hours*3600];
    opts = odeset('RelTol',1e-12,'AbsTol',1e-15);
    [t_orb, X_orb] = ode113(@(t,x) orbit_dynamics(t,x,env), tspan, [r0; v0], opts);
    r_tab = X_orb(:,1:3);
    v_tab = X_orb(:,4:6);
    
    % == PRE-COMPUTATION
    jd0 = juliandate(sim_start_date);
    gmst0 = mod(280.46061837 + 360.98564736629*(jd0 - 2451545.0), 360);
    m_ecef_unit = [cos(lat_mag)*cos(lon_mag); cos(lat_mag)*sin(lon_mag); sin(lat_mag)];
    N_pts = length(t_orb);
    B_tab = zeros(N_pts,3); S_tab = zeros(N_pts,3);
    rho_tab = zeros(N_pts,1); elev_tab = zeros(N_pts,1);
    for i=1:N_pts
        % ECI to lla
        current_time = sim_start_date + seconds(t_orb(i));
        theta = deg2rad(gmst0) + env.we * t_orb(i);
        R_eci_to_ecef = [cos(theta) sin(theta) 0; -sin(theta) cos(theta) 0; 0 0 1];
        R_ecef_to_eci = R_eci_to_ecef';
        r_eci = r_tab(i,:)';
        r_ecef = R_eci_to_ecef * r_eci;
        lla = ecef2lla(r_ecef');    
        alt = lla(3);   
        % Apply 2024 model for future dates
        model_decyear = min(decyear(current_time), 2024.99); 
        model_year = min(year(current_time), 2024);   
        % Magnetic Field
        if alt < alt_limit_B
            B_ned = igrfmagm(alt/1000, lla(1), lla(2), model_decyear, '13');
            B_ned = B_ned(:) * 1e-9; 
            lat = deg2rad(lla(1)); lon = deg2rad(lla(2));
            R_ned_to_ecef = [-sin(lat)*cos(lon), -sin(lon), -cos(lat)*cos(lon); -sin(lat)*sin(lon),  cos(lon), -cos(lat)*sin(lon); cos(lat),           0,        -sin(lat)]';
            B_tab(i,:) = (R_ecef_to_eci * R_ned_to_ecef * B_ned)';
        else
            m_eci = R_ecef_to_eci * m_ecef_unit * M_earth;
            B_tab(i,:) = ((mu0 / (4 * pi * norm(r_eci)^3)) * (3 * dot(m_eci, r_eci/norm(r_eci)) * (r_eci/norm(r_eci)) - m_eci))';
        end
        % Atmosphere
        if alt < alt_end_fade
            [~, d] = atmosnrlmsise00(alt, lla(1), lla(2), model_year, day(current_time, 'dayofyear'), seconds(timeofday(current_time)), f107ave, f107, ap);
            fade = 1.0;
            if alt > alt_start_fade, fade = 0.5 * (1 + cos(pi * (alt - alt_start_fade) / (alt_end_fade - alt_start_fade))); end
            rho_tab(i) = d(6) * fade;
        end
        % Sun ECI
        S_tab(i,:) = sun_vector_eci(current_time);
        % Site elevation
        r_site_ecef = env.Re * [cos(site_lat)*cos(site_lon); cos(site_lat)*sin(site_lon); sin(site_lat)];
        r_site_eci = R_ecef_to_eci * r_site_ecef;
        rho_vec = r_eci - r_site_eci;
        elev_tab(i) = rad2deg(asin(dot(rho_vec/norm(rho_vec), r_site_eci/norm(r_site_eci))));
    end
    % Interpolation
    B_fun = griddedInterpolant(t_orb, B_tab, 'pchip');
    S_fun = griddedInterpolant(t_orb, S_tab, 'pchip');
    rho_fun = griddedInterpolant(t_orb, rho_tab, 'pchip');
    r_fun = griddedInterpolant(t_orb, r_tab, 'pchip');
    v_fun = griddedInterpolant(t_orb, v_tab, 'pchip');
    
    % == ATTITUDE PROPAGATION
    sat.invI = inv(sat.I);
    if ~strcmp(sat.attitude_mode, 'dynamics')
        env.flags.gg   = false;
        env.flags.srp  = false;
        env.flags.drag = false;
        q0 = [0; 0; 0; 1]; 
        w0 = [0; 0; 0]; 
    end
    if strcmp(sat.attitude_mode, 'nadir') || strcmp(sat.attitude_mode, 'follow_site')
        t = t_orb; 
        n = length(t); 
        Y = zeros(n, 7);
    
        for i = 1:n
            r_eci = r_tab(i,:)'; 
            v_eci = v_tab(i,:)';
    
            % ==============================================================
            % +Z body = asse di puntamento
            % ==============================================================
    
            if strcmp(sat.attitude_mode, 'follow_site') && elev_tab(i) > elev_threshold
                theta_g = deg2rad(gmst0) + env.we * t(i); 
                R3_theta = [cos(theta_g) -sin(theta_g) 0; 
                            sin(theta_g)  cos(theta_g) 0; 
                            0             0            1];
    
                r_site_ecef = env.Re * [cos(site_lat)*cos(site_lon); 
                                        cos(site_lat)*sin(site_lon); 
                                        sin(site_lat)];
    
                r_site_eci = R3_theta * r_site_ecef;
    
                % +Z body verso il target
                z_b = r_site_eci - r_eci;
                z_b = z_b / norm(z_b);
            else
                % +Z body verso il nadir
                z_b = -r_eci / norm(r_eci);
            end
    
            % ==============================================================
            % +X body circa along-track, proiettato ortogonale a +Z
            % ==============================================================
    
            x_b = v_eci - dot(v_eci, z_b) * z_b;
    
            if norm(x_b) < 1e-12
                x_b = cross([0; 0; 1], z_b);
                if norm(x_b) < 1e-12
                    x_b = cross([1; 0; 0], z_b);
                end
            end
    
            x_b = x_b / norm(x_b);
    
            % ==============================================================
            % +Y completa la terna destrorsa
            % ==============================================================
    
            y_b = cross(z_b, x_b);
            y_b = y_b / norm(y_b);
    
            % Ri-ortogonalizza X
            x_b = cross(y_b, z_b);
            x_b = x_b / norm(x_b);
    
            % Colonne = assi body espressi in ECI
            R_body_to_eci = [x_b y_b z_b];
    
            % Quaternione interno MATLAB: Body -> ECI
            q_wxyz_b2eci = rotm2quat(R_body_to_eci);
    
            % Stato Y salva [qx qy qz qw]
            Y(i, 1:4) = [q_wxyz_b2eci(2), ...
                         q_wxyz_b2eci(3), ...
                         q_wxyz_b2eci(4), ...
                         q_wxyz_b2eci(1)];
    
            orb_rate = norm(cross(r_eci, v_eci)) / norm(r_eci)^2;
            Y(i, 5:7) = (R_body_to_eci' * [0; -orb_rate; 0])';
        end
    else
        [t, Y] = ode113(@(t,y) attitude_dynamics(t,y,sat,env,B_fun,S_fun,rho_fun,r_fun,v_fun), ...
                        tspan, [q0; w0], opts);
    end   
    % == POST-PROCESSING
    wlog = Y(:,5:7); 
    n = length(t);
    eul = zeros(n,3); Mlog_all = zeros(n,6); alt = zeros(n,1);
    elevations = zeros(n,1); 
    offsets = zeros(n,1); 
    target_offsets = zeros(n,1);
    
    site_sun_elevations = zeros(n,1);
    site_is_day = false(n,1);
    % Angular Momentum Preallocation
    H_body = zeros(n,3); H_eci  = zeros(n,3); H_mag  = zeros(n,1); H_dir  = zeros(n,3);
    for i=1:n
        % Torques
        [~, M_vecs] = attitude_dynamics(t(i), Y(i,:)', sat, env, B_fun, S_fun, rho_fun, r_fun, v_fun);
        Mlog_all(i,:) = vecnorm(M_vecs, 2, 1);
        % Quaternions and Euler Angles
        q = Y(i,1:4)'; q = q/norm(q);
        eul(i,:) = quat2eul([q(4) q(1:3)'], 'ZYX');
        A = quat2dcm(q');  
        % Position in ECI and ECEF
        r_vec = r_fun(t(i))'; alt(i) = norm(r_vec) - env.Re;    
        theta_g = deg2rad(gmst0) + env.we * t(i); 
        R3_theta = [cos(theta_g) -sin(theta_g) 0; sin(theta_g) cos(theta_g) 0; 0 0 1];
        r_site_ecef = env.Re * [cos(site_lat)*cos(site_lon); cos(site_lat)*sin(site_lon); sin(site_lat)];
        r_site_eci = R3_theta * r_site_ecef;   
        rho_vec = r_vec - r_site_eci;
        elevations(i) = rad2deg(asin(dot(rho_vec/norm(rho_vec), r_site_eci/norm(r_site_eci))));
        % Sun elevation over target site
        current_time = sim_start_date + seconds(t(i));
        S_eci_now = sun_vector_eci(current_time);
        S_eci_now = S_eci_now / norm(S_eci_now);
        
        site_normal_eci = r_site_eci / norm(r_site_eci);
        
        site_sun_elevations(i) = rad2deg(asin(dot(S_eci_now, site_normal_eci)));
        
        % Day/night classification at target site
        site_is_day(i) = site_sun_elevations(i) >= sun_elev_threshold_deg;
        % Offset
        z_body_eci = A(:,3); z_nadir_eci = -r_vec / norm(r_vec);
        offsets(i) = atan2d(norm(cross(z_body_eci, z_nadir_eci)), dot(z_body_eci, z_nadir_eci));
        z_target_eci = (r_site_eci - r_vec) / norm(r_site_eci - r_vec);
        target_offsets(i) = atan2d(norm(cross(z_body_eci, z_target_eci)), dot(z_body_eci, z_target_eci));
        % Round at zero
        if offsets(i) < 1e-10
            offsets(i) = 0; 
        end
        if target_offsets(i) < 1e-10
            target_offsets(i) = 0; 
        end
        % Angular Momentum
        w_b = wlog(i,:)'; 
        H_body(i,:) = (sat.I * w_b)'; 
        H_mag(i) = norm(H_body(i,:)); 
        H_eci(i,:) = (A * H_body(i,:)')'; 
        H_dir(i,:) = H_eci(i,:) / H_mag(i); 
    end
    
    %% == OUTPUT ==============================================================
    mask = elevations > elev_threshold;
    d = diff([0; mask; 0]); 
    start_idx = find(d == 1); 
    end_idx = find(d == -1) - 1;
    
    if isempty(start_idx)
        fprintf('Warning: No passage found over %d deg threshold. Export entire simulation.\n', elev_threshold);
        idx_pass = 1:n;
        best_peak = max(elevations);
    else
        best_peak = -inf;
        idx_pass = [];
        best_sun_elev_at_peak = NaN;
    
        for i_p = 1:length(start_idx)
            curr_range = start_idx(i_p):end_idx(i_p);
    
            % Classifico il passaggio usando l'istante di massima elevazione
            [peak, local_peak_idx] = max(elevations(curr_range));
            peak_idx = curr_range(local_peak_idx);
    
            pass_is_day_full = all(site_sun_elevations(curr_range) >= sun_elev_threshold_deg);
            pass_is_night_full = all(site_sun_elevations(curr_range) < sun_elev_threshold_deg);
            
            if sun_constraint_enabled
                if sun_constraint_mode == "day"
                    pass_ok = pass_is_day_full;
                elseif sun_constraint_mode == "night"
                    pass_ok = pass_is_night_full;
                else
                    pass_ok = true;
                end
            else
                pass_ok = true;
            end
    
            if pass_ok && peak > best_peak
                best_peak = peak;
                idx_pass = curr_range;
                best_sun_elev_at_peak = site_sun_elevations(peak_idx);
            end
        end
    
        if isempty(idx_pass)
            error('No passage found satisfying Sun_Constraint_Mode = "%s" with Sun_Elevation_Threshold_Deg = %.2f deg.', ...
                  sun_constraint_mode, sun_elev_threshold_deg);
        end
    
        if sun_constraint_enabled
            fprintf('Selected %s passage. Peak elevation: %.2f deg. Site Sun elevation at peak: %.2f deg.\n', ...
                    sun_constraint_mode, best_peak, best_sun_elev_at_peak);
        else
            fprintf('Selected best elevation passage. Peak elevation: %.2f deg. Site Sun elevation at peak: %.2f deg.\n', ...
                    best_peak, best_sun_elev_at_peak);
        end
    end

    % == MULTI-ENGINE CSV EXPORT ==============================================
    fid_eci    = fopen(output_plot + "\output_attitude_propagation_ECI.csv", 'w');
    fid_unity  = fopen(output_plot + "\output_attitude_propagation_Unity.csv", 'w');
    fid_unreal = fopen(out_dir + "\output_attitude_propagation.csv", 'w');
    
    % Intestazioni colonne
    header = 'timestamp_utc,eci_x_km,eci_y_km,eci_z_km,q_w,q_x,q_y,q_z,nadir_offset_deg\n';
    fprintf(fid_eci, 'timestamp_utc,eci_x_km,eci_y_km,eci_z_km,q_w,q_x,q_y,q_z,nadir_offset_deg\n');
    fprintf(fid_unity, header);
    fprintf(fid_unreal, header);
    
    for k = idx_pass
        ts = sim_start_date + seconds(t(k));
        time_str = datestr(ts, 'yyyy-mm-ddTHH:MM:SSZ');
        r_km = r_fun(t(k)) / 1000;
        
        % Estrazione quaterno dall'integratore: lo stato Y memorizza [qx, qy, qz, qw]
        q = Y(k,1:4); q = q/norm(q);
        qx = q(1); qy = q(2); qz = q(3); qw = q(4);
        
        % 1. CSV Originale (Coordinate ECI standard - Destrorse, Z-up)
        fprintf(fid_eci, '%s,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.2f\n', ...
            time_str, r_km(1), r_km(2), r_km(3), qw, qx, qy, qz, offsets(k));
        
        % 2. CSV per Unity (Sistema Sinistrorso, Y-up: X->X, Y->Z, Z->Y)
        % Trasformazione quaternione (qw, qx, qy, qz) -> (qw, -qx, -qz, -qy) per cambio assi e mano
        r_unity = [r_km(1), r_km(2), r_km(3)];
        qw_u = qw; qx_u = -qx; qy_u = -qz; qz_u = -qy;
        fprintf(fid_unity, '%s,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.2f\n', ...
            time_str, r_unity(1), r_unity(2), r_unity(3), qw_u, qx_u, qy_u, qz_u, offsets(k));
        
        % 3. CSV per Unreal Engine (Sistema Sinistrorso, Z-up: X->X, Y->-Y, Z->Z)
        % Trasformazione quaternione (qw, qx, qy, qz) -> (qw, -qx, qy, -qz) per inversione asse Y
        r_unreal = [r_km(1), r_km(2), r_km(3)];
        
        qw_ue =  qw;
        qx_ue = -qx;
        qy_ue = -qy;
        qz_ue = -qz;
        fprintf(fid_unreal, '%s,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.2f\n', ...
            time_str, r_unreal(1), r_unreal(2), r_unreal(3), qw_ue, qx_ue, qy_ue, qz_ue, offsets(k));
    end
    fclose(fid_eci);
    fclose(fid_unity);
    fclose(fid_unreal);
    
    fprintf('CSV ''output_attitude_propagation.csv'' saved successfully (Max Elevation: %.2f°)\n', best_peak);
    fprintf('CSV ''output_attitude_propagation_Unity.csv'' saved successfully in output folder.\n');
    fprintf('CSV ''output_attitude_propagation_ECI.csv'' saved successfully in output folder.\n');
    
    % == TERMINAL REPORT
    idx_per = alt < (min(alt) + 200e3);
    idx_apo = alt > (max(alt) - 2000e3);
    names = {'GG', 'SRP', 'Drag'};
    fprintf('\n--- Mean Torques [Nm] ---\n');
    fprintf('%-20s | %-12s | %-12s\n', 'Perturbation', 'Mean Perigee', 'Mean Apogee');
    fprintf('------------------------------------------------------------\n');
    for k=1:3
        fprintf('%-20s | %-12.2e | %-12.2e\n', names{k}, mean(Mlog_all(idx_per,k)), mean(Mlog_all(idx_apo,k)));
    end
    fprintf('\nSimulation completed in: %.2f s\n', toc(total_tic));
    
    %% == PLOTS ===============================================================
    
    % Forzatura del tema chiaro per tutte le figure
    set(groot, 'DefaultFigureColor', 'w');
    set(groot, 'DefaultAxesColor', 'w');
    set(groot, 'DefaultAxesXColor', 'k');
    set(groot, 'DefaultAxesYColor', 'k');
    set(groot, 'DefaultAxesZColor', 'k');
    set(groot, 'DefaultTextColor', 'k');
    set(groot, 'DefaultLegendColor', 'w');
    set(groot, 'DefaultLegendTextColor', 'k');
    set(groot, 'DefaultLegendEdgeColor', [0.5 0.5 0.5]);
    set(groot, 'DefaultAxesGridColor', [0.1 0.1 0.1]);
    set(groot, 'DefaultAxesGridAlpha', 0.20);
    set(groot, 'DefaultAxesMinorGridColor', [0.3 0.3 0.3]); 

    f1 = figure('Color', [0.94 0.94 0.94], 'Visible', 'off');
    subplot(3,2,1); plot(t/3600, rad2deg(wlog)); grid on; grid minor; xlabel('Time [h]'); ylabel('Angular Velocity [deg/s]'); title('Angular Velocity'); legend('w_x','w_y','w_z');
    subplot(3,2,2); plot(t/3600, rad2deg(eul)); grid on; grid minor; xlabel('Time [h]'); ylabel('Euler Angles [deg]'); title('Euler Angles'); legend('Z','Y','X');
    subplot(3,2,3); plot(t/3600, Mlog_all(:,[1,2,4])); grid on; grid minor; xlabel('Time [h]'); ylabel('Torques [Nm]'); title('Torques (Linear)'); legend('GG','SRP','Drag');
    subplot(3,2,4); semilogy(t/3600, Mlog_all(:,[1,2,4])+1e-25); grid on; grid minor; xlabel('Time [h]'); ylabel('Torques [Nm]'); title('Torques (Log)'); ylim([1e-15 1e-4]); legend('GG','SRP','Drag');
    subplot(3,2,5); plot(t/3600, 0.5 * sum((wlog * sat.I) .* wlog, 2)); grid on; grid minor; xlabel('Time [h]'); ylabel('Rotational Energy [J]'); title('Rotational Energy');
    subplot(3,2,6); plot(t/3600, alt/1000); grid on; grid minor; xlabel('Time [h]'); ylabel('Altitude [km]'); title('Altitude');
    saveas(f1, fullfile(output_plot, '01_telemetry.png')); close(f1);

    f2 = figure('Color', 'w', 'Name', 'Environment & Tracking', 'Visible', 'off');
    subplot(3,1,1); plot(t/3600, elevations, 'LineWidth', 1.5); grid on; ylabel('Elevation [deg]'); title('Ground Station Elevation Profile');
    subplot(3,1,2); plot(t/3600, offsets, 'LineWidth', 1.5, 'Color', [0.85 0.33 0.1]); grid on; ylabel('Nadir Offset [deg]'); title('Nadir Pointing Error');
    subplot(3,1,3); plot(t/3600, target_offsets, 'LineWidth', 1.5, 'Color', [0.2 0.6 0.2]); grid on; ylabel('Target Offset [deg]'); title('Target Pointing Error'); xlabel('Time [h]');
    saveas(f2, fullfile(output_plot, '02_tracking.png')); close(f2);

    f3 = figure('Color', 'w', 'Name', 'Angular Momentum', 'Visible', 'off');
    subplot(2,1,1); plot(t/3600, H_mag, 'k', 'LineWidth', 1.5); title('Angular Momentum Modulus'); xlabel('Time [h]'); ylabel('|H| [Nms]'); grid on; grid minor;
    subplot(2,1,2); plot(t/3600, H_dir(:,1), 'r', 'LineWidth', 1.2); hold on; plot(t/3600, H_dir(:,2), 'g', 'LineWidth', 1.2); plot(t/3600, H_dir(:,3), 'b', 'LineWidth', 1.2); title('Angular Momentum Direction (ECI)'); xlabel('Time [h]'); ylabel('Components'); legend('H_x', 'H_y', 'H_z', 'Location', 'best'); grid on; grid minor;
    saveas(f3, fullfile(output_plot, '03_angular_momentum.png')); close(f3);

    % Groundtrack and 3D orbit ECI and ECEF
    r_km = r_fun(t) / 1000;
    plot_groundtrack(site_lat, site_lon, r_km, t, deg2rad(gmst0), start_idx, end_idx, output_plot);
    plot_3d_eci(env, gmst0, site_lat, site_lon, t, r_fun, start_idx, end_idx, output_plot)
    plot_3d_ecef(env, gmst0, site_lat, site_lon, t, r_fun, start_idx, end_idx, output_plot)

    % == DASHBOARD DATA EXPORT ==============================================
    % Export all numerical data required by the STAR HTML dashboard.
    export_attitude_dashboard_data(output_plot, cfg, sim_start_date, t, wlog, eul, Mlog_all, sat, alt, ...
        elevations, offsets, target_offsets, H_mag, H_dir, r_fun, env, gmst0, site_lat, site_lon, ...
        start_idx, end_idx, best_peak, idx_pass);

end

%% =======================================================================%
% == FUNCTIONS ============================================================
%=========================================================================%
function [dY, M_out] = attitude_dynamics(t,Y,sat,env,B_fun,S_fun,rho_fun,r_fun,v_fun)
    persistent last_print; if isempty(last_print), last_print = -3600*6; end
    if t - last_print >= 3600*6, fprintf('Simulation time: %.1f hours\n', t/3600); last_print = t; end
    
    q = Y(1:4); q = q/norm(q); w = Y(5:7);
    r_eci = r_fun(t)'; v_eci = v_fun(t)';
    r_mag = norm(r_eci); A = quat2dcm(q'); 
    % Transofrmation in Body ref
    S_eci = S_fun(t)'; S_hat = S_eci/norm(S_eci); S_b = A'*S_hat;
    in_shadow = dot(S_hat, r_eci/r_mag) < -sqrt(1-(env.Re/r_mag)^2);
    v_rel_eci = v_eci - cross([0; 0; env.we], r_eci);
    v_rel_b = A' * v_rel_eci; 
    % 1. Gravity gradient (GG)
    M_gg = [0; 0; 0];
    if env.flags.gg
        M_gg = 3*(env.mu/r_mag^5)*cross(A'*r_eci, sat.I*(A'*r_eci));
    end    
    % 2. Solar radiation pressure (SRP)
    M_srp = [0; 0; 0];
    if env.flags.srp && ~in_shadow
        F_srp_b = -env.P_sun * sat.A_ref * sat.Cr * S_b;
        M_srp = cross(sat.r_cp, F_srp_b);
    end  
    % 3. Atmospheric Drag (DRAG)
    M_drag = [0; 0; 0];
    if env.flags.drag
        rho = rho_fun(t);
        v_mag = norm(v_rel_b);
        if v_mag > 0
            F_drag_b = -0.5 * rho * sat.Cd * sat.A_ref * v_mag * v_rel_b;
            M_drag = cross(sat.r_cp, F_drag_b);
        end
    end   
    % Euler Equations
    dw = sat.invI*(M_gg + M_srp + M_drag - cross(w,sat.I*w));
    dq = 0.5 * [q(4)*w + cross(q(1:3),w); -dot(q(1:3),w)];
    dY = [dq; dw];  
    % Output
    M_out = [M_gg, M_srp, zeros(3,1), M_drag, zeros(3,1), zeros(3,1)];
end

function dY = orbit_dynamics(t,Y,env)
    r = Y(1:3); v = Y(4:6); rmag = norm(r);
    z = r(3); rmag2 = rmag^2;    
    % Two-body acceleration (Ideal Keplerian Earth)
    a0 = -env.mu / rmag^3 * r;
    aJ2 = [0; 0; 0];
    aJ3 = [0; 0; 0];    
    if isfield(env.flags, 'pert') && env.flags.pert
        % J2 Perturbation (Oblateness)
        if isfield(env.flags, 'j2') && env.flags.j2
            f2 = 1.5 * env.J2 * env.mu * env.Re^2 / rmag^5;
            aJ2 = f2 * [r(1) * (5 * z^2 / rmag2 - 1); ...
                        r(2) * (5 * z^2 / rmag2 - 1); ...
                        z * (5 * z^2 / rmag2 - 3)];
        end
        % J3 Perturbation (Pear-shaped Earth Profile)
        if isfield(env.flags, 'j3') && env.flags.j3
            f3 = 0.5 * env.J3 * env.mu * env.Re^3 / rmag^5;
            z_r = z / rmag;
            aJ3 = f3 * [r(1) * z_r * (35 * z_r^2 - 15) / rmag; ...
                        r(2) * z_r * (35 * z_r^2 - 15) / rmag; ...
                        (35 * z_r^4 - 30 * z_r^2 + 3)];
        end
    end
    dY = [v; a0 + aJ2 + aJ3];
end

function [r,v]=coe2rv(coe,mu)
    r_p=(coe.a*(1-coe.e^2))/(1+coe.e*cos(coe.nu));
    r_per=[r_p*cos(coe.nu); r_p*sin(coe.nu);0];
    v_per=sqrt(mu/(coe.a*(1-coe.e^2)))*[-sin(coe.nu); coe.e+cos(coe.nu);0];
    R=(rot_z(coe.omega)*rot_x(coe.i)*rot_z(coe.RAAN))';
    r=R*r_per; v=R*v_per;
end

function M=rot_z(a), M=[cos(a) sin(a) 0; -sin(a) cos(a) 0; 0 0 1]; end
function M=rot_x(a), M=[1 0 0;0 cos(a) sin(a);0 -sin(a) cos(a)]; end

function s_eci=sun_vector_eci(dt)
    jd=juliandate(dt); n=jd-2451545.0;
    L=mod(280.460+0.9856474*n,360); g=mod(357.528+0.9856003*n,360);
    lambda=L+1.915*sin(deg2rad(g))+0.020*sin(deg2rad(2*g));
    eps=23.439-0.0000004*n;
    s_eci=[cos(deg2rad(lambda)); sin(deg2rad(lambda))*cos(deg2rad(eps)); sin(deg2rad(lambda))*sin(deg2rad(eps))];
end

function A=quat2dcm(q)
    q=q/norm(q); x=q(1); y=q(2); z=q(3); w=q(4);
    A=[1-2*(y^2+z^2) 2*(x*y-z*w) 2*(x*z+y*w); 2*(x*y+z*w) 1-2*(x^2+z^2) 2*(y*z-x*w); 2*(x*z-y*w) 2*(y*z+x*w) 1-2*(x^2+y^2)];
end

function q = rotm2quat(R)
    tr = R(1,1) + R(2,2) + R(3,3);
    if (tr > 0)
        S = sqrt(tr+1.0) * 2; qw = 0.25 * S; qx = (R(3,2) - R(2,3)) / S; qy = (R(1,3) - R(3,1)) / S; qz = (R(2,1) - R(1,2)) / S;
    elseif ((R(1,1) > R(2,2))&&(R(1,1) > R(3,3)))
        S = sqrt(1.0 + R(1,1) - R(2,2) - R(3,3)) * 2; qw = (R(3,2) - R(2,3)) / S; qx = 0.25 * S; qy = (R(1,2) + R(2,1)) / S; qz = (R(1,3) + R(3,1)) / S;
    elseif (R(2,2) > R(3,3))
        S = sqrt(1.0 + R(2,2) - R(1,1) - R(3,3)) * 2; qw = (R(1,3) - R(3,1)) / S; qx = (R(1,2) + R(2,1)) / S; qy = 0.25 * S; qz = (R(2,3) + R(3,2)) / S;
    else
        S = sqrt(1.0 + R(3,3) - R(1,1) - R(2,2)) * 2; qw = (R(2,1) - R(1,2)) / S; qx = (R(1,3) + R(3,1)) / S; qy = (R(2,3) + R(3,2)) / S; qz = 0.25 * S;
    end
    q = [qw, qx, qy, qz];
end

function plot_groundtrack(site_lat, site_lon, eci_km_array, times_array, theta_0_rad, start_idx, end_idx, output_dir)
    om_e = 7.2921159e-5;
    num_pts = size(eci_km_array,1);
    lat_deg = zeros(num_pts,1); lon_deg = zeros(num_pts,1); 
    for k = 1:num_pts
        theta = theta_0_rad + om_e * times_array(k);
        R_ecef = [cos(theta) sin(theta) 0; -sin(theta) cos(theta) 0; 0 0 1];
        r_ecef = R_ecef * eci_km_array(k,:)';
        lon_deg(k) = rad2deg(atan2(r_ecef(2), r_ecef(1)));
        lat_deg(k) = rad2deg(atan2(r_ecef(3), sqrt(r_ecef(1)^2 + r_ecef(2)^2)));
    end
    lon_deg = mod(lon_deg + 180, 360) - 180;
    
    f = figure('Color', 'w', 'Name', 'Ground Track', 'Visible', 'off'); 
    hold on;
    try
        load coastlines;
        plot(coastlon, coastlat, 'Color', [0.5 0.5 0.5]);
    catch
        grid on; grid minor;
    end   
    % Complete groundtrack (blu)
    plot(lon_deg, lat_deg, 'b', 'LineWidth', 1.5);     
    % Coverages (green)
    for i_p = 1:length(start_idx)
        idx = start_idx(i_p):end_idx(i_p);
        lon_pass = lon_deg(idx);
        lat_pass = lat_deg(idx);
        % Avoid +180 -> -180
        wrap_idx = find(abs(diff(lon_pass)) > 180);
        if ~isempty(wrap_idx)
            lon_pass = [lon_pass(1:wrap_idx); NaN; lon_pass(wrap_idx+1:end)];
            lat_pass = [lat_pass(1:wrap_idx); NaN; lat_pass(wrap_idx+1:end)];
        end        
        plot(lon_pass, lat_pass, 'Color', [0 0.8 0], 'LineWidth', 3.5);
    end
    % Site   
    plot(rad2deg(site_lon), rad2deg(site_lat), 'ro', 'MarkerFaceColor', 'r');
    text(rad2deg(site_lon)+0.01, rad2deg(site_lat)+0.01, 'GS', 'Color', 'r', 'FontWeight', 'bold');
    title('Ground Track');
    xlabel('Longitude [deg]'); ylabel('Latitude [deg]');
    grid on; grid minor; axis equal; axis([-180 180 -90 90]);
    saveas(f, fullfile(output_dir, '04_ground_track.png')); close(f);
end

function plot_3d_ecef(env, gmst0, site_lat, site_lon, t, r_fun, start_idx, end_idx, output_dir)
    f = figure('Color', 'w', 'Name', '3D Orbit & Target Tracking', 'Position', [150 100 800 600], 'Visible', 'off');
    % 1. Plot Earth Sphere (Light Blue)
    [X_sphere, Y_sphere, Z_sphere] = sphere(50);
    surf(X_sphere*env.Re/1000, Y_sphere*env.Re/1000, Z_sphere*env.Re/1000, 'FaceColor', [0.8 0.9 1], 'EdgeColor', 'none', 'FaceAlpha', 0.85);
    hold on; grid on; axis equal;
    xlabel('X [km]'); ylabel('Y [km]'); zlabel('Z [km]');
    title('3D Orbit and Coverage (ECEF Frame)');
    % 2. Add Coastlines (Dark Blue)
    try
        load coastlines;
        [x_coast, y_coast, z_coast] = sph2cart(deg2rad(coastlon), deg2rad(coastlat), env.Re/1000 + 5); 
        plot3(x_coast, y_coast, z_coast, 'Color', [0 0.2 0.6], 'LineWidth', 1);
    catch
        warning('Mapping toolbox non trovato, salto le coastlines.');
    end
    % Compute ECEF paths
    n = length(t);
    r_ecef_full = zeros(n, 3); r_gnd_full  = zeros(n, 3);
    for k = 1:n
        theta = deg2rad(gmst0) + env.we * t(k);
        R_eci2ecef = [cos(theta) sin(theta) 0; -sin(theta) cos(theta) 0; 0 0 1];
        r_ecef_full(k,:) = (R_eci2ecef * r_fun(t(k))')';
        r_gnd_full(k,:)  = env.Re * r_ecef_full(k,:) / norm(r_ecef_full(k,:));
    end
    % 3. Plot Full Orbit & Ground Track
    plot3(r_ecef_full(:,1)/1000, r_ecef_full(:,2)/1000, r_ecef_full(:,3)/1000, 'Color', [0.6 0.6 0.6], 'LineWidth', 1);
    plot3(r_gnd_full(:,1)/1000, r_gnd_full(:,2)/1000, r_gnd_full(:,3)/1000, 'Color', [0.3 0.3 0.3], 'LineWidth', 1, 'LineStyle', ':');
    % 4. Highlight Coverage Segments (Loop avoids connecting lines across passes)
    for i_p = 1:length(start_idx)
        idx = start_idx(i_p):end_idx(i_p);
        plot3(r_ecef_full(idx,1)/1000, r_ecef_full(idx,2)/1000, r_ecef_full(idx,3)/1000, 'Color', [0 0.8 0], 'LineWidth', 3);
        plot3(r_gnd_full(idx,1)/1000, r_gnd_full(idx,2)/1000, r_gnd_full(idx,3)/1000, 'Color', [1 0.6 0], 'LineWidth', 3);
    end
    % 5. Plot Ground Station (Genoa)
    r_site_ecef = env.Re * [cos(site_lat)*cos(site_lon); cos(site_lat)*sin(site_lon); sin(site_lat)];
    plot3(r_site_ecef(1)/1000, r_site_ecef(2)/1000, r_site_ecef(3)/1000, 'r^', 'MarkerSize', 8, 'MarkerFaceColor','r');
    text(r_site_ecef(1)/1000, r_site_ecef(2)/1000, (r_site_ecef(3)/1000)+600, ' GS', 'Color', 'r', 'FontWeight', 'bold');
    max_r = max(vecnorm(r_ecef_full'))/1000;
    xlim([-max_r max_r]); ylim([-max_r max_r]); zlim([-max_r max_r]);
    view(15, 35);
    saveas(f, fullfile(output_dir, '05_orbit_3d_ecef.png')); close(f);
end

function plot_3d_eci(env, gmst0, site_lat, site_lon, t, r_fun, start_idx, end_idx, output_dir)
    f = figure('Color', 'w', 'Name', '3D Orbit (ECI Frame)', 'Position', [150 100 800 600], 'Visible', 'off');   
    % 1. Plot Earth Sphere (Light Blue)
    [X_sphere, Y_sphere, Z_sphere] = sphere(50);
    surf(X_sphere*env.Re/1000, Y_sphere*env.Re/1000, Z_sphere*env.Re/1000, ...
        'FaceColor', [0.8 0.9 1], 'EdgeColor', 'none', 'FaceAlpha', 0.85);
    hold on; grid on; axis equal;
    xlabel('X [km]'); ylabel('Y [km]'); zlabel('Z [km]');
    title('3D Orbit (ECI Inertial Frame)');  
    % 2. Add Coastlines (Rotated to ECI at t=0)
    try
        load coastlines;
        [x_coast, y_coast, z_coast] = sph2cart(deg2rad(coastlon), deg2rad(coastlat), env.Re/1000 + 5); 
        % Matrice di rotazione ECEF -> ECI al tempo t=0
        R_ecef2eci_0 = [cos(deg2rad(gmst0)) -sin(deg2rad(gmst0)) 0; 
                        sin(deg2rad(gmst0))  cos(deg2rad(gmst0)) 0; 
                        0                    0                   1];
        coast_eci = (R_ecef2eci_0 * [x_coast'; y_coast'; z_coast'])';
        plot3(coast_eci(:,1), coast_eci(:,2), coast_eci(:,3), 'Color', [0 0.2 0.6], 'LineWidth', 1);
    catch
        warning('Mapping toolbox not found, skip coastlines.');
    end    
    % 3. Plot Full Orbit in ECI (r_fun(t) is already ECI)
    r_eci_full = r_fun(t);
    plot3(r_eci_full(:,1)/1000, r_eci_full(:,2)/1000, r_eci_full(:,3)/1000, 'Color', [0.6 0.6 0.6], 'LineWidth', 1.5);    
    % 4. Highlight Coverage Segments (Green)
    for i_p = 1:length(start_idx)
        idx = start_idx(i_p):end_idx(i_p);
        plot3(r_eci_full(idx,1)/1000, r_eci_full(idx,2)/1000, r_eci_full(idx,3)/1000, 'Color', [0 0.8 0], 'LineWidth', 3);
    end
    % 5. Plot Ground Station (Genoa at t=0)
    r_site_ecef = env.Re * [cos(site_lat)*cos(site_lon); cos(site_lat)*sin(site_lon); sin(site_lat)];
    r_site_eci_0 = R_ecef2eci_0 * r_site_ecef; % Rotate GS to ECI at t=0
    plot3(r_site_eci_0(1)/1000, r_site_eci_0(2)/1000, r_site_eci_0(3)/1000, 'r^', 'MarkerSize', 8, 'MarkerFaceColor','r');
    text(r_site_eci_0(1)/1000, r_site_eci_0(2)/1000, (r_site_eci_0(3)/1000)+600, ' GS (t=0)', 'Color', 'r', 'FontWeight', 'bold'); 
    view(15, 35);
    saveas(f, fullfile(output_dir, '06_orbit_3d_eci.png')); close(f);
end

function export_attitude_dashboard_data(output_dir, cfg, sim_start_date, t, wlog, eul, Mlog_all, sat, alt, ...
        elevations, offsets, target_offsets, H_mag, H_dir, r_fun, env, gmst0, site_lat, site_lon, ...
        start_idx, end_idx, best_peak, idx_pass)
    % EXPORT_ATTITUDE_DASHBOARD_DATA
    % Generates a JSON and a JavaScript file for the STAR HTML dashboard.
    %
    % Output files:
    %   attitude_propagation_plots_data.json
    %   attitude_propagation_plots_data.js
    %
    % The JavaScript file defines:
    %   window.attitudePropagationData = {...};

    if ~exist(output_dir, 'dir')
        mkdir(output_dir);
    end

    t = t(:);
    n = numel(t);
    time_h = t / 3600;

    r_eci_m = r_fun(t);
    r_eci_km = r_eci_m / 1000;

    r_ecef_km = zeros(n, 3);
    r_ground_ecef_km = zeros(n, 3);
    ground_lat_deg = zeros(n, 1);
    ground_lon_deg = zeros(n, 1);

    for k = 1:n
        theta = deg2rad(gmst0) + env.we * t(k);
        R_eci_to_ecef = [cos(theta) sin(theta) 0; -sin(theta) cos(theta) 0; 0 0 1];
        r_ecef_m = R_eci_to_ecef * r_eci_m(k,:)';
        r_ecef_km(k,:) = (r_ecef_m / 1000)';
        r_ground_ecef_km(k,:) = (env.Re * r_ecef_m / norm(r_ecef_m) / 1000)';

        ground_lon_deg(k) = rad2deg(atan2(r_ecef_m(2), r_ecef_m(1)));
        ground_lat_deg(k) = rad2deg(atan2(r_ecef_m(3), sqrt(r_ecef_m(1)^2 + r_ecef_m(2)^2)));
    end
    ground_lon_deg = mod(ground_lon_deg + 180, 360) - 180;

    coverage = struct([]);
    for i_p = 1:length(start_idx)
        idx = start_idx(i_p):end_idx(i_p);
        coverage(i_p).start_index = start_idx(i_p);
        coverage(i_p).end_index = end_idx(i_p);
        coverage(i_p).time_h = time_h(idx);
        coverage(i_p).ground_lon_deg = ground_lon_deg(idx);
        coverage(i_p).ground_lat_deg = ground_lat_deg(idx);
        coverage(i_p).r_eci_km = r_eci_km(idx,:);
        coverage(i_p).r_ecef_km = r_ecef_km(idx,:);
        coverage(i_p).r_ground_ecef_km = r_ground_ecef_km(idx,:);
    end

    energy_J = 0.5 * sum((wlog * sat.I) .* wlog, 2);

    torque_linear = struct();
    torque_linear.gravity_gradient_Nm = Mlog_all(:,1);
    torque_linear.solar_radiation_pressure_Nm = Mlog_all(:,2);
    torque_linear.drag_Nm = Mlog_all(:,4);

    mean_torques = struct();
    idx_per = alt < (min(alt) + 200e3);
    idx_apo = alt > (max(alt) - 2000e3);
    mean_torques.perigee.gravity_gradient_Nm = mean(Mlog_all(idx_per,1));
    mean_torques.perigee.solar_radiation_pressure_Nm = mean(Mlog_all(idx_per,2));
    mean_torques.perigee.drag_Nm = mean(Mlog_all(idx_per,4));
    mean_torques.apogee.gravity_gradient_Nm = mean(Mlog_all(idx_apo,1));
    mean_torques.apogee.solar_radiation_pressure_Nm = mean(Mlog_all(idx_apo,2));
    mean_torques.apogee.drag_Nm = mean(Mlog_all(idx_apo,4));

    dashboard = struct();
    dashboard.summary = struct();
    dashboard.summary.module = 'STAR END-003 Attitude Propagator';
    dashboard.summary.sim_start_date = datestr(sim_start_date, 'yyyy-mm-dd HH:MM:SS');
    dashboard.summary.sim_hours = cfg.sim_hours;
    dashboard.summary.attitude_mode = cfg.sat.attitude_mode;
    dashboard.summary.best_elevation_deg = best_peak;
    dashboard.summary.elevation_threshold_deg = cfg.target.elev_threshold;
    dashboard.summary.sample_count = n;
    dashboard.summary.exported_pass_sample_count = numel(idx_pass);

    dashboard.input = cfg;

    dashboard.time_s = t;
    dashboard.time_h = time_h;
    dashboard.angular_velocity_deg_s = rad2deg(wlog);
    dashboard.euler_angles_deg = rad2deg(eul);
    dashboard.torques = torque_linear;
    dashboard.rotational_energy_J = energy_J;
    dashboard.altitude_km = alt / 1000;
    dashboard.elevation_deg = elevations;
    dashboard.nadir_offset_deg = offsets;
    dashboard.target_offset_deg = target_offsets;
    dashboard.angular_momentum = struct();
    dashboard.angular_momentum.magnitude_Nms = H_mag;
    dashboard.angular_momentum.direction_eci = H_dir;

    dashboard.orbit = struct();
    dashboard.orbit.r_eci_km = r_eci_km;
    dashboard.orbit.r_ecef_km = r_ecef_km;
    dashboard.orbit.r_ground_ecef_km = r_ground_ecef_km;
    dashboard.orbit.ground_lon_deg = ground_lon_deg;
    dashboard.orbit.ground_lat_deg = ground_lat_deg;
    dashboard.orbit.coverage = coverage;

    dashboard.site = struct();
    dashboard.site.lat_deg = rad2deg(site_lat);
    dashboard.site.lon_deg = rad2deg(site_lon);
    dashboard.site.elev_threshold_deg = cfg.target.elev_threshold;
    dashboard.site.r_ecef_km = (env.Re * [cos(site_lat)*cos(site_lon); cos(site_lat)*sin(site_lon); sin(site_lat)] / 1000)';

    dashboard.report = struct();
    dashboard.report.mean_torques = mean_torques;

    dashboard.png_outputs = {'01_telemetry.png', '02_tracking.png', '03_angular_momentum.png', ...
        '04_ground_track.png', '05_orbit_3d_ecef.png', '06_orbit_3d_eci.png'};

    json_text = jsonencode(dashboard);
    json_file = fullfile(output_dir, 'attitude_propagation_plots_data.json');
    fid = fopen(json_file, 'w');
    if fid < 0
        error('Unable to open dashboard JSON output file: %s', json_file);
    end
    fprintf(fid, '%s', json_text);
    fclose(fid);

    js_file = fullfile(output_dir, 'attitude_propagation_plots_data.js');
    fid = fopen(js_file, 'w');
    if fid < 0
        error('Unable to open dashboard JS output file: %s', js_file);
    end
    fprintf(fid, 'window.attitudePropagationData = %s;\n', json_text);
    fclose(fid);

    fprintf('Dashboard data saved: %s\n', js_file);
end
