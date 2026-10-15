%% Help ----------------------------------------------------------------- %
% Simple Eulerian propagator given initial attitude conditions and body
% inertia
%
% Inertia: att0     [double 7x1]   array [q0; w0] scalar first
%          tsim     [double Nx1]   array of simulation times
%          I        [double 3x3]   inertia matrix
%
% Output:  att      [double 4xN]   attitude (quaternions)
% ----------------------------------------------------------------------- %
function att = propAttitude(att0, tsim, I)
    
    prop.I = I;
    % Start-end data points
    tspan = tsim;
    % Initial conditions
    y0 = att0;
    % Integrate
    options = odeset('AbsTol', 1e-5, 'RelTol', 1e-5);
    [~,x] = ode45(@(t,y0) eul_integrator(t,y0,prop), tspan, y0, options);
    att   = x(:,1:7);

end

function dy = eul_integrator(t, y, prop)

dy = zeros(7,1);
I  = prop.I;

% Quaternions
dy(1)   = -0.5*dot(y(5:7),y(2:4));
dy(2:4) = 0.5*(eye(3)*y(1) + skewmat(y(2:4)))*y(5:7);

% Angular velocity
T = [0;0;0];
dy(5:7) = I\(T - cross(y(5:7),I*y(5:7)));
end

%% Help ------------------------------------------------------------------%
% 
% Compute the skew symmetric matrix of a 3x1 vector                     
% 
% INPUT:  a - [double 3x1] - input vector
% OUTPUT: A - [double 3x3] - skew symmetric matrix
%
% ------------------------------------------------------------------------%

function A = skewmat(a)

a = a(:);

if length(a) ~= 3
    error('The input vector must be a 3 by 1 vector');
end

A = [0,    -a(3),  a(2);
     a(3),  0,    -a(1);
    -a(2),  a(1),  0];
end