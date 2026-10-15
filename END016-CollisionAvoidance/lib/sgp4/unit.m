function [outvec] = unit ( vec )

small = 0.000001;
magv = mag(vec);
if ( magv > small )
    for i= 1: 3
        outvec(i)= vec(i)/magv;
    end
else
    for i= 1: 3
        outvec(i)= 0.0;
    end
end

