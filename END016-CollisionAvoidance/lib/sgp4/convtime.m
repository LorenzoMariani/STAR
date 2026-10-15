% ------------------------------------------------------------------------------
%
%                           function convtime
%
%  this function finds the time parameters and julian century values for inputs
%    of utc or ut1. numerous outputs are found as shown in the local variables.
%    because calucations are in utc, you must include timezone if ( you enter a
%    local time, otherwise it should be zero.
%
%  author        : david vallado                  719-573-2600    4 jun 2002
%
%  revisions
%    vallado     - add tcg, tcb, etc                              6 oct 2005
%    vallado     - fix documentation for dut1                     8 oct 2002
%
%  inputs          description                    range / units
%    year        - year                           1900 .. 2100
%    mon         - month                          1 .. 12
%    day         - day                            1 .. 28,29,30,31
%    hr          - universal time hour            0 .. 23
%    min         - universal time min             0 .. 59
%    sec         - universal time sec (utc)            0.0  .. 59.999
%    timezone    - offset to utc from local site  0 .. 23 hr
%    dut1        - delta of ut1 - utc             sec
%    dat         - delta of tai - utc             sec
%
%  outputs       :
%    ut1         - universal time                 sec
%    tut1        - julian centuries of ut1
%    jdut1       - julian date (days only)           days from 4713 bc
%    jdut1Frac   - julian date (fraction of a day)   days from 0 hr of the day
%    utc         - coordinated universal time     sec
%    tai         - atomic time                    sec
%    tdt         - terrestrial dynamical time     sec
%    ttdt        - julian centuries of tdt
%    jdtt        - julian date (days only)           days from 4713 bc
%    jdttFrac    - julian date (fraction of a day)   days from 0 hr of the day
%    tdb         - terrestrial barycentric time   sec
%    ttdb        - julian centuries of tdb
%    jdtdb       - julian date of tdb             days from 4713 bc
%    tcb         - celestial barycentric time     sec
%    tcg         - celestial geocentric time      sec
%    jdtdb       - julian date (days only)           days from 4713 bc
%    jdtdbFrac   - julian date (fraction of a day)   days from 0 hr of the day
%
%  locals        :
%    hrtemp      - temporary hours                hr
%    mintemp     - temporary minutes              min
%    sectemp     - temporary seconds              sec
%    localhr     - difference to local time       hr
%    jd          - julian date of request         days from 4713 bc
%    me          - mean anomaly of the earth      rad
%
%  coupling      :
%    hms_2_sec   - conversion between hr-min-sec .and. seconds
%    jday        - find the julian date
%
%  references    :
%    vallado       2007, 201, alg 16, ex 3-7
%
% [ut1, tut1, jdut1,jdut1frac, utc, tai, tt, ttt, jdtt,jdttfrac, tdb, ttdb, jdtdb,jdtdbfrac, tcg, jdtcg,jdtcgfrac, tcb, jdtcb,jdtcbfrac ] ...
% = convtime ( year, mon, day, hr, min, sec, timezone, dut1, dat );
% ------------------------------------------------------------------------------

function [jdut1, jdut1frac, ttt] = convtime ( year, mon, day, hr, min, sec, timezone, dut1, dat )

localhr = timezone + hr;
utc     = hms2sec( localhr, min, sec );

ut1     = utc + dut1;
[hrtemp,mintemp,sectemp] = sec2hms(ut1);
[jdut1, jdut1frac]       = jday(year, mon, day, hrtemp, mintemp, sectemp);

tai = utc + dat;


tt  = tai + 32.184;
[hrtemp,mintemp,sectemp] = sec2hms( tt );
[jdtt, jdttfrac] = jday(year,mon,day, hrtemp, mintemp, sectemp);
ttt              = (jdtt + jdttfrac - 2451545.0)/36525.0;
