function plot_results(residuals, P, m, sigma,obj,count)

if count == 1
    ii = 1;
else 
    ii = 3;
end

dt = [];
r  = [];
it = [];
ct = [];

for i=1:length(residuals)
    dt  = [dt, residuals(7,:)];
    r   = [r,  residuals(1,:)];
    it  = [it, residuals(2,:)];
    ct  = [ct, residuals(3,:)];
end

figure(ii)
plot(dt,r,'r+')
hold on
plot(dt,it,'bo')
hold on
plot(dt,ct,'k*')
str = sprintf("Residuals - RIC system - ID: %s", obj);
title(str);
xlabel("dt wrt primary TLE")
ylabel("Residuals [km]")
legend("radial", "in-track", "cross-track")
grid on
grid minor

h = figure(ii+1);
h = plot_gaussian_ellipsoid(m, P, sigma);