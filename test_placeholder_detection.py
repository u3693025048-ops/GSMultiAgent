#!/usr/bin/env python3
"""Test placeholder sim_s detection and injection."""

import sys
sys.path.insert(0, r'c:\Users\Lenovo\Desktop\SCI1\code\code\xiao\GSMultiAgent13-V0.2')

from multi_agent.rl.matlab_rl_optimizer import MatlabRLOptimizer

# Test 1: Placeholder sim_s (from iter2)
placeholder_sim_s = """
function r = sim_s(p)
% placeholder simulation (to be replaced with actual dynamics)
% returns a struct with expected fields
r.miss = 100*rand;
r.peak_ny = 30+5*randn;
r.pitch_pm = 45+5*randn;
r.bw_pitch = 10+randn;
r.gm_pitch = 6+randn;
end
"""

# Test 2: Real sim_s (from KB template)
real_sim_s = """
function res=sim_s(p)
dt=0.002; tt=70; t=0;
XK=[p.V0,p.upsilon0,p.gama0,p.phi0,p.theta0,p.phiv0,0,0,0,p.x0,p.y0,p.z0];
T=[p.T_x0;p.T_y0;p.T_z0];
gs=cg(p);
cs=struct('Ee_ay',0,'Ee_az',0,'ul',p.upsilon0,'pl',p.phi0,'ddx',0,'ddy',0,'ddz',0);
mn=inf; Xm=XK; Tm=T; tm=0; mp=inf; pny=0; i=0;
while t<tt
    i=i+1; t=t+dt;
    XK=real(rk4f(XK,dt,p,cs.ddz,cs.ddy,cs.ddx));
    TVz=p.T_Vz_amp*cos(p.T_Vz_freq*t);
    T=T+[p.T_Vx;p.T_Vy;TVz]*dt;
    [N1,N2,G1,G2,gc]=gf(T(1),T(2),T(3),XK,p.T_Vx,p.T_Vy,TVz,p.N_pn);
    [~,~,~,cs,ny]=cf(XK,N1,N2,G1,G2,gc,gs,dt,cs,p);
    pny=max(pny,ny);
    mn2=norm(XK(10:12)'-T);
    if mn2<mn; mn=mn2; Xm=XK; Tm=T; tm=t; end
    if mn2<5; break; end
    if i>10&&mn2>mp&&mn2>mn*1.5; break; end
    mp=mn2;
end
res=struct('miss',mn,'t_impact',tm,'peak_ny',pny,'pitch_pm',gs.pm_pitch,'bw_pitch',gs.bw_pitch,'gm_pitch',gs.gm_pitch);
end
"""

# Test 3: Script with placeholder that needs injection
script_with_placeholder = """
function main()
clc; close all;
N_MC = 100;
base = struct('x0', 0, 'y0', 9000);
for i = 1:N_MC
    r = sim_s(base);
end
end

function r = sim_s(p)
% placeholder
r.miss = 0;
r.peak_ny = 0;
r.pitch_pm = 60;
r.bw_pitch = 25;
r.gm_pitch = 6;
end
"""

print("=" * 80)
print("Testing placeholder detection and injection...")
print("=" * 80)

# Test 1: Placeholder detection
is_placeholder, content = MatlabRLOptimizer._detect_placeholder_sim_s(placeholder_sim_s)
print(f"\nTest 1 - Placeholder sim_s detection:")
print(f"  Detected as placeholder: {is_placeholder}")
print(f"  Expected: True")
print(f"  Result: {'✓ PASS' if is_placeholder else '✗ FAIL'}")

# Test 2: Real sim_s detection
is_placeholder, content = MatlabRLOptimizer._detect_placeholder_sim_s(real_sim_s)
print(f"\nTest 2 - Real sim_s detection:")
print(f"  Detected as placeholder: {is_placeholder}")
print(f"  Expected: False")
print(f"  Result: {'✓ PASS' if not is_placeholder else '✗ FAIL'}")

# Test 3: Verify detection works on script with placeholder
import os
print(f"\nTest 3 - Detection on full script:")
is_placeholder, _ = MatlabRLOptimizer._detect_placeholder_sim_s(script_with_placeholder)
print(f"  Script with placeholder detected: {is_placeholder}")
print(f"  Expected: True")
print(f"  Result: {'✓ PASS' if is_placeholder else '✗ FAIL'}")

print("\n" + "=" * 80)
print("All tests completed!")
print("=" * 80)
