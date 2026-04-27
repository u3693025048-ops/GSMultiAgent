function chengxu_robust_analysis_singlefile
% 严格以原chengxu程序为主链条，不改原命中逻辑
% 仅增加：
% 1) 时域性能指标
% 2) 多工作点线性鲁棒性分析
% 3) 参数摄动分析
%


clc;
clear;
close all;

%% ================= 原程序中的全局变量 =================
global Jx Jy Jz m S L g beta alpha gamav C45 P dt gamac
global upsilon_last Ee_ay phi_last Ee_az ay_body ayc_body gama_max az_body azc_body
global deltax deltay deltaz

%% ================= 弹体参数初始化（保持原程序） =================
Jx=56.7;Jy=3996;Jz=3996;m=1030; S=0.094519;L=1.71;g=9.8;P=6350;C45=180/pi;

%% ================= 初始条件（保持原程序） =================
y=7000;x=0;z=0;V=960;
deltax=0;deltay=0;deltaz=0;
upsilon=-0/C45;gama=0/C45;phi=0/C45;theta=-0/C45;phiv=0;

upsilon_last=upsilon;
phi_last=phi;
Ee_az=0;
Ee_ay=0;
gama_max=45/C45;

wx=0;wy=0;wz=0;

beta=asin(cos(theta)*(cos(gama)*sin(phi-phiv)+sin(upsilon)*sin(gama)*cos(phi-phiv))-sin(theta)*cos(upsilon)*sin(gama));
alpha=asin((cos(theta)*(sin(upsilon)*cos(gama)*cos(phi-phiv)-sin(gama)*sin(phi-phiv))-sin(theta)*cos(upsilon)*cos(gama))/cos(beta));
gamav=asin(1/cos(theta)*(cos(alpha)*sin(beta)*sin(upsilon)-sin(alpha)*sin(beta)*cos(gama)*cos(upsilon)+cos(beta)*sin(gama)*cos(upsilon)));

%% ================= 仿真条件（保持原程序） =================
t=0;i=0;tt=55;dt=0.002;

%% ================= 目标初始位置（保持原程序） =================
T_x=20000;T_y=2000;T_z=5000;

%% ================= 状态量初始化（保持原程序） =================
XK=zeros(1,12);
XK(1)=V;XK(2)=upsilon;XK(3)=gama;XK(4)=phi;XK(5)=theta;XK(6)=phiv;
XK(7)=wx;XK(8)=wy;XK(9)=wz;
XK(10)=x;XK(11)=y;XK(12)=z;

%% ================= 原程序线化+驾驶仪设计（保持原程序） =================
[linBase, autoBase] = Missile_transfer_function_local(V,y,struct());
canshu = Three_loop_autopilot_local(V,linBase,autoBase);

miss_min = inf;
miss_min_index = 1;
hitFlag = 0;
failFlag = 0;

Track = nan(ceil(tt/dt)+5, 40);

%% ================= 主循环：严格保持原程序时序 =================
while t<tt
    i=i+1;
    t=t+dt;

    V=XK(1);upsilon=XK(2);gama=XK(3);phi=XK(4);theta=XK(5);phiv=XK(6);
    wx=XK(7);wy=XK(8);wz=XK(9);
    x=XK(10);y=XK(11);z=XK(12);

    % ===== 保持原程序：先积分 =====
    XK1=RK4(XK,dt);

    % ===== 保持原程序：用当前状态计算角度 =====
    beta=asin(cos(theta)*(cos(gama)*sin(phi-phiv)+sin(upsilon)*sin(gama)*cos(phi-phiv))-sin(theta)*cos(upsilon)*sin(gama));
    alpha=asin((cos(theta)*(sin(upsilon)*cos(gama)*cos(phi-phiv)-sin(gama)*sin(phi-phiv))-sin(theta)*cos(upsilon)*cos(gama))/cos(beta));
    gamav=asin(1/cos(theta)*(cos(alpha)*sin(beta)*sin(upsilon)-sin(alpha)*sin(beta)*cos(gama)*cos(upsilon)+cos(beta)*sin(gama)*cos(upsilon)));

    % ===== 保持原程序：目标运动 =====
    T_Vx=250;T_Vy=50;T_Vz=50*cos(0.2*t);

    % ===== 保持原程序：更新状态 =====
    XK=XK1;
    T_x=T_x+T_Vx*dt;
    T_y=T_y+T_Vy*dt;
    T_z=T_z+T_Vz*dt;

    % ===== 保持原程序：制导 =====
    [Nyc_1,Nzc_1,Nyc_G,Nzc_G,gamac]= guidance_local(T_x,T_y,T_z,XK,T_Vx,T_Vy,T_Vz);

    % ===== 保持原程序：控制 =====
    [deltax,deltay,deltaz]=control(XK,Nyc_1,Nzc_1,Nyc_G,Nzc_G,gamac,canshu);

    Track(i,1)=t;
    Track(i,2)=x;
    Track(i,3)=y;
    Track(i,4)=V;
    Track(i,5)=alpha;
    Track(i,6)=upsilon;
    Track(i,7)=gama;
    Track(i,8)=phi;
    Track(i,9)=wz;
    Track(i,10)=deltaz;
    Track(i,11)=deltay;
    Track(i,12)=z;
    Track(i,13)=deltax;
    Track(i,14)=T_x;
    Track(i,15)=T_y;
    Track(i,16)=T_z;
    Track(i,17)=ay_body;
    Track(i,18)=ayc_body;
    Track(i,19)=az_body;
    Track(i,20)=azc_body;
    Track(i,21)=beta;
    Track(i,22)=gamac;

    % 为鲁棒性分析额外记录，不影响原主链条
    Track(i,23)=XK(5);   % theta
    Track(i,24)=XK(6);   % phiv
    Track(i,25)=XK(7);   % wx
    Track(i,26)=XK(8);   % wy
    Track(i,27)=T_Vx;
    Track(i,28)=T_Vy;
    Track(i,29)=T_Vz;
    Track(i,30)=sqrt((x-T_x)^2+(y-T_y)^2+(z-T_z)^2);

    miss_now = sqrt((x-T_x)^2+(y-T_y)^2+(z-T_z)^2);
    if miss_now < miss_min
        miss_min = miss_now;
        miss_min_index = i;
    end

    if sqrt((x-T_x)^2+(y-T_y)^2+(z-T_z)^2)<5
        hitFlag = 1;
        break
    end

    if any(~isfinite(XK))
        failFlag = 1;
        break
    end
end

Track = Track(1:i,:);

%% ================= 原程序终端指标 + 增强时域指标 =================
timeMetrics = evaluate_time_metrics_local(XK,T_x,T_y,T_z,t,Track,miss_min,miss_min_index);

fprintf('\n================ 终端指标 ================\n');
fprintf('仿真终止时间 t = %.4f s\n', t);
fprintf('最终脱靶量 miss_distance = %.4f m\n', timeMetrics.miss_distance);
fprintf('最小脱靶量 miss_min = %.4f m\n', timeMetrics.miss_min);
fprintf('最小脱靶量对应时刻 = %.4f s\n', Track(miss_min_index,1));
fprintf('终端角误差(速度方向-视线方向) = %.4f deg\n', timeMetrics.terminal_angle_error);
fprintf('终端角误差(导弹速度-目标速度) = %.4f deg\n', timeMetrics.terminal_velocity_angle_error);
fprintf('终端俯仰角误差 = %.4f deg\n', timeMetrics.theta_error_end);
fprintf('终端方位角误差 = %.4f deg\n', timeMetrics.phiv_error_end);
fprintf('最大攻角 = %.4f deg\n', timeMetrics.alpha_max_deg);
fprintf('最大侧滑角 = %.4f deg\n', timeMetrics.beta_max_deg);
fprintf('舵偏角最大值 = %.4f deg\n', timeMetrics.delta_max_deg);
fprintf('舵偏角饱和占比 = %.4f %%\n', 100*timeMetrics.delta_sat_ratio);
fprintf('法向过载跟踪误差积分 J_ay = %.4f\n', timeMetrics.J_ay);
fprintf('侧向过载跟踪误差积分 J_az = %.4f\n', timeMetrics.J_az);
fprintf('控制能量指标 Ju = %.4f\n', timeMetrics.Ju);
fprintf('是否命中 = %d\n', hitFlag);
fprintf('是否异常终止 = %d\n', failFlag);
fprintf('==========================================\n');

%% ================= 新增：多工作点线性鲁棒性分析 =================
linReport = multi_point_linear_analysis_local(Track);

fprintf('\n================ 多工作点线性鲁棒性分析 ================\n');
for k = 1:length(linReport.points)
    p = linReport.points(k);
    fprintf('\n---- 工作点 %d: %s ----\n', k, p.name);
    fprintf('[俯仰] PM = %.4f deg, GM = %.4f dB, BW = %.4f rad/s\n', ...
        p.pitch.Pm_deg, p.pitch.Gm_dB, p.pitch.BW);
    fprintf('[偏航] PM = %.4f deg, GM = %.4f dB, BW = %.4f rad/s\n', ...
        p.yaw.Pm_deg, p.yaw.Gm_dB, p.yaw.BW);
    fprintf('[滚转] PM = %.4f deg, GM = %.4f dB, BW = %.4f rad/s\n', ...
        p.roll.Pm_deg, p.roll.Gm_dB, p.roll.BW);
end
fprintf('\n=========================================================\n');

%% ================= 新增：参数摄动鲁棒性分析 =================
robustScan = param_robust_scan_local();

%% ================= 画图：保留原图 + 新增鲁棒性分析图 =================
plot_original_results_local(Track,t);
plot_linear_results_local(linReport);
plot_param_robust_results_local(robustScan);

end

%% ========================================================================
%% Missile_transfer_function
%% ========================================================================
function [lin, auto] = Missile_transfer_function_local(V,y,paramScale)

global Jx Jy Jz m S L C45 P

if nargin < 3 || isempty(paramScale)
    paramScale = struct();
end

if ~isfield(paramScale,'CLA')
    paramScale.CLA = 1.0;
end
if ~isfield(paramScale,'mza')
    paramScale.mza = 1.0;
end
if ~isfield(paramScale,'mass')
    paramScale.mass = 1.0;
end
if ~isfield(paramScale,'push')
    paramScale.push = 1.0;
end

m_use = m * paramScale.mass;
P_use = P * paramScale.push;

rou=1.2495*(1-0.0065*y/288.15)^4.25588;
q=0.5*rou*V^2;

CLA=0.6303*paramScale.CLA; CLDZ=0.068651;
mza=-0.06982*paramScale.mza; mzdz=-0.21195;
mzwz=0;
CZB=-0.31; CZDY=-0.07921;
myb=-0.19948; mydx=0.249; mydy=-0.236;
mywy=0; mywx=0;
mxb=-0.00248;
mxdx=-0.02547;
mxdy=0.001061;
mxwx=0;
mxwy=0;

CLA=CLA*C45;CLDZ=CLDZ*C45;
mza=mza*C45;mzdz=mzdz*C45;
CZB=CZB*C45;CZDY=CZDY*C45;CZDX=0;
myb=myb*C45;mydx=mydx*C45;mydy=mydy*C45;
mxb=mxb*C45;mxdx=mxdx*C45;mxdy=mxdy*C45;

a_alpha=-mza*q*S*L/Jz;
a_deltaz=-mzdz*q*S*L/Jz;
a_wz=-mzwz*q*S*L^2/Jz/V;
b_alpha=(P_use+CLA*q*S)/m_use/V;
b_deltaz=CLDZ*q*S/m_use/V;

a_beta=-myb*q*S*L/Jy;
a_deltay=-mydy*q*S*L/Jy;
a_wy=-mywy*q*S*L^2/Jy/V;
b_beta=(P_use-CZB*q*S)/m_use/V;
b_deltay=-CZDY*q*S/m_use/V;

a_wx=-mywx*q*S*L^2/Jy/V;
a_deltax=-mydx*q*S*L/Jy;
b_deltax=CZDX*q*S/m_use/V;

c_deltax=-mxdx*q*S*L/Jx;
c_wx=-mxwx*q*S*L^2/Jx/V;
c_beta=-mxb*q*S*L/Jx;
c_deltay=-mxdy*q*S*L/Jx;
c_wy=-mxwy*q*S*L^2/Jx/V;

Tm=1/sqrt(a_alpha+a_wz*b_alpha);
wm=sqrt(a_alpha+a_wz*b_alpha);
zetam=(a_wz+b_alpha)/2*Tm;
A2=-b_deltaz/(a_deltaz*b_alpha-a_alpha*b_deltaz);
A1=a_wz*A2;
kdot_upsilon=-(a_deltaz*b_alpha-a_alpha*b_deltaz)/(a_alpha+a_wz*b_alpha);
ka=V*kdot_upsilon;
Tdot_upsilon=a_deltaz/(a_deltaz*b_alpha-a_alpha*b_deltaz);
kalpha=-(a_wz*b_deltaz+a_deltaz)/(a_alpha+a_wz*b_alpha);
Talpha=b_deltaz/(a_wz*b_deltaz+a_deltaz);
G_deltaz_ay=tf(ka*[A2 A1 1],[Tm^2 2*Tm*zetam 1]);

Tp=1/sqrt(a_beta+a_wy*b_beta);
wp=sqrt(a_beta+a_wy*b_beta);
zetap=(a_wy+b_beta)/2*Tp;
A2p=-b_deltay/(a_deltay*b_beta-a_beta*b_deltay);
A1p=a_wy*A2p;
kdot_phi=-(a_deltay*b_beta-a_beta*b_deltay)/(a_beta+a_wy*b_beta);
kp=-V*kdot_phi;
Tdot_phi=a_deltay/(a_deltay*b_beta-a_beta*b_deltay);
kbeta=-(a_wy*b_deltay+a_deltay)/(a_beta+a_wy*b_beta);
Tbeta=b_deltay/(a_wy*b_deltay+a_deltay);
G_deltay_az=tf(kp*[A2p A1p 1],[Tp^2 2*Tp*zetap 1]);

G_deltax_gama=tf(-c_deltax,[1 c_wx 0]);

lin = struct();
lin.Tm=Tm; lin.wm=wm; lin.zetam=zetam; lin.A2=A2; lin.A1=A1;
lin.kdot_upsilon=kdot_upsilon; lin.Tdot_upsilon=Tdot_upsilon;
lin.Tp=Tp; lin.wp=wp; lin.zetap=zetap; lin.A2p=A2p; lin.A1p=A1p;
lin.kdot_phi=kdot_phi; lin.Tdot_phi=Tdot_phi;
lin.c_deltax=c_deltax; lin.c_wx=c_wx;
lin.G_deltaz_ay = G_deltaz_ay;
lin.G_deltay_az = G_deltay_az;
lin.G_deltax_gama = G_deltax_gama;

auto = struct();
end


%% ========================================================================
%% Three_loop_autopilot
%% ========================================================================
function canshu = Three_loop_autopilot_local(V,lin,auto)

Tm=lin.Tm; wm=lin.wm; zetam=lin.zetam; A2=lin.A2; A1=lin.A1;
kdot_upsilon=lin.kdot_upsilon; Tdot_upsilon=lin.Tdot_upsilon;
Tp=lin.Tp; wp=lin.wp; zetap=lin.zetap; A2p=lin.A2p; A1p=lin.A1p;
kdot_phi=lin.kdot_phi; Tdot_phi=lin.Tdot_phi;
c_deltax=lin.c_deltax; c_wx=lin.c_wx;

w1=14;zeta1=0.75;tao1=0.2;KACT=-1;c=0;Kac=1;
M0=w1^2/wm^2/tao1;
M1=(tao1+2*zeta1/w1)*M0-1;
M2=(1/w1^2+2*zeta1*tao1/w1)*M0-2*zetam/wm;
juzhen1=[M2;M1;M0];
juzhen3=KACT*kdot_upsilon*[Tdot_upsilon c*Kac*Tdot_upsilon+Kac*V*A2 0;1 c*Kac+Kac*V*A1 Tdot_upsilon;0 Kac*V 1];
juzhen2=inv(juzhen3)*juzhen1;
Kg=juzhen2(1);
KA=juzhen2(2);
WI=juzhen2(3);
KDC=WI/KA/V+Kac;
G_ayc_ay=KDC*KACT*kdot_upsilon*V*KA*tf([A2 A1 1],[Tm^2 2*Tm*zeta1+M2 1+M1 M0]);

w2=12;zeta2=0.75;tao2=0.2;KACT=-1;c=0;Kacp=1;
M0p=w2^2/wp^2/tao2;
M1p=(tao2+2*zeta2/w2)*M0p-1;
M2p=(1/w2^2+2*zeta2*tao2/w2)*M0p-2*zetap/wp;
juzhen1p=[M2p;M1p;M0p];
juzhen3p=KACT*kdot_phi*[Tdot_phi c*Kacp*Tdot_phi-Kacp*V*A2p 0;1 c*Kacp-Kacp*V*A1p Tdot_phi;0 -Kacp*V 1];
juzhen2p=inv(juzhen3p)*juzhen1p;
Kgp=juzhen2p(1);
KAp=juzhen2p(2);
WIp=juzhen2p(3);
KDCp=-WIp/KAp/V+Kacp;
G_azc_az=-KDCp*KACT*kdot_phi*V*KAp*tf([A2p A1p 1],[Tp^2 2*Tp*zeta2+M2p 1+M1p M0p]);

w3=14;zeta3=0.7;KACT=-1;c=0;Kacg=1;
Kgama=w3^2/(-KACT*c_deltax);
Kwx=(c_wx-2*zeta3*w3)/(KACT*c_deltax);
G_gamac_gama=tf(-KACT*c_deltax*Kgama,[1 c_wx-KACT*c_deltax*Kwx -KACT*c_deltax*Kgama]);

canshu = [Kg,KA,WI,KDC,Kgp,KAp,WIp,KDCp,Kgama,Kwx,KACT];

% 供鲁棒性分析用
assignin('base','G_ayc_ay_local',G_ayc_ay);
assignin('base','G_azc_az_local',G_azc_az);
assignin('base','G_gamac_gama_local',G_gamac_gama);
end

%% ========================================================================
%% guidance
%% ========================================================================
function [Nyc_1,Nzc_1,Nyc_G,Nzc_G,gamac] = guidance_local(T_x,T_y,T_z,XK,T_Vx,T_Vy,T_Vz)
global gama_max ayc_body azc_body
g=9.8;
V=XK(1);upsilon=XK(2);gama=XK(3);phi=XK(4);theta=XK(5);phiv=XK(6);
x=XK(10);y=XK(11);z=XK(12);

Vx_A=V*cos(theta)*cos(phiv);
Vy_A=V*sin(theta);
Vz_A=-V*cos(theta)*sin(phiv);
R=sqrt((x-T_x)^2+(y-T_y)^2+(z-T_z)^2);
Vrx=T_Vx-Vx_A;
Vry=T_Vy-Vy_A;
Vrz=T_Vz-Vz_A;
qx_dot=((T_y-y)*Vrz-(T_z-z)*Vry)/R^2;
qy_dot=((T_z-z)*Vrx-(T_x-x)*Vrz)/R^2;
qz_dot=((T_x-x)*Vry-(T_y-y)*Vrx)/R^2;

axc_A=0;
ayc_A=3*sqrt(Vrx^2+Vry^2)*qz_dot;
azc_A=-3*sqrt(Vrx^2+Vrz^2)*qy_dot;

ayc_body=(-sin(upsilon)*cos(phi)*cos(gama)+sin(phi)*sin(gama))*axc_A+cos(upsilon)*cos(gama)*ayc_A+(sin(upsilon)*sin(phi)*cos(gama)+cos(phi)*sin(gama))*azc_A;
azc_body=(sin(upsilon)*cos(phi)*sin(gama)+sin(phi)*cos(gama))*axc_A-cos(upsilon)*sin(gama)*ayc_A+(cos(phi)*cos(gama)-sin(upsilon)*sin(phi)*sin(gama))*azc_A;

if abs(R)<7000
    a=0;
else
    a=1;
end

switch a
    case{1}
        gamac=atan(azc_body/ayc_body);
        if abs(gamac)>gama_max
            gamac=sign(gamac)*gama_max;
        end
        Nyc_1=sqrt(ayc_body^2+azc_body^2)/g*sign_nonzero_local(ayc_body);
        Nzc_1=0;
        Nyc_G=cos(upsilon)*cos(gama);
        Nzc_G=-cos(upsilon)*sin(gama);
    otherwise
        gamac=0;
        Nyc_1=ayc_body/g;
        Nzc_1=azc_body/g;
        Nyc_G=cos(upsilon)*cos(gama);
        Nzc_G=-cos(upsilon)*sin(gama);
end
end

%% ========================================================================
%% 新增：时域性能分析模块
%% ========================================================================
function metrics = evaluate_time_metrics_local(XK,T_x,T_y,T_z,t,Track,miss_min,miss_min_index)

V_end = XK(1);
theta_end = XK(5);
phiv_end = XK(6);
x_end = XK(10);
y_end = XK(11);
z_end = XK(12);

miss_distance = sqrt((x_end - T_x)^2 + (y_end - T_y)^2 + (z_end - T_z)^2);

Vm_x = V_end * cos(theta_end) * cos(phiv_end);
Vm_y = V_end * sin(theta_end);
Vm_z = V_end * cos(theta_end) * sin(phiv_end);
Vm_vec = [Vm_x, Vm_y, Vm_z];

T_Vx_end = 250;
T_Vy_end = 50;
T_Vz_end = 50*cos(0.2*t);
Vt_vec = [T_Vx_end, T_Vy_end, T_Vz_end];

R_vec = [T_x - x_end, T_y - y_end, T_z - z_end];

cos_err1 = dot(Vm_vec, R_vec) / max(norm(Vm_vec) * norm(R_vec),1e-8);
cos_err1 = max(min(cos_err1,1),-1);
terminal_angle_error = acos(cos_err1) * 180/pi;

if norm(Vt_vec) > 1e-6
    cos_err2 = dot(Vm_vec, Vt_vec) / max(norm(Vm_vec) * norm(Vt_vec),1e-8);
    cos_err2 = max(min(cos_err2,1),-1);
    terminal_velocity_angle_error = acos(cos_err2) * 180/pi;
else
    terminal_velocity_angle_error = NaN;
end

Rxy = sqrt((T_x-x_end)^2 + (T_z-z_end)^2);
theta_los = atan2((T_y-y_end), Rxy);
phiv_los = atan2((T_z-z_end), (T_x-x_end));

theta_error_end = (theta_end - theta_los) * 180/pi;
phiv_error_end = (phiv_end - phiv_los) * 180/pi;

dt = Track(2,1)-Track(1,1);
alpha = Track(:,5);
beta = Track(:,21);
deltaz = Track(:,10);
deltay = Track(:,11);
deltax = Track(:,13);
ay = Track(:,17);
ayc = Track(:,18);
az = Track(:,19);
azc = Track(:,20);

J_ay = sum(abs(ayc-ay))*dt;
J_az = sum(abs(azc-az))*dt;
Ju   = sum(deltax.^2 + deltay.^2 + deltaz.^2)*dt;

delta_all = [abs(deltax), abs(deltay), abs(deltaz)];
delta_max_deg = max(delta_all(:))*180/pi;
delta_sat_ratio = mean(abs(deltax) >= 15*pi/180 | abs(deltay) >= 15*pi/180 | abs(deltaz) >= 15*pi/180);

metrics = struct();
metrics.t_end = t;
metrics.miss_distance = miss_distance;
metrics.miss_min = miss_min;
metrics.t_miss_min = Track(miss_min_index,1);
metrics.terminal_angle_error = terminal_angle_error;
metrics.terminal_velocity_angle_error = terminal_velocity_angle_error;
metrics.theta_error_end = theta_error_end;
metrics.phiv_error_end = phiv_error_end;
metrics.alpha_max_deg = max(abs(alpha))*180/pi;
metrics.beta_max_deg = max(abs(beta))*180/pi;
metrics.delta_max_deg = delta_max_deg;
metrics.delta_sat_ratio = delta_sat_ratio;
metrics.J_ay = J_ay;
metrics.J_az = J_az;
metrics.Ju = Ju;
end

%% ========================================================================
%% 新增：多工作点线性鲁棒性分析
%% ========================================================================
function linReport = multi_point_linear_analysis_local(Track)

N = size(Track,1);
idxList = [1, round(N/2), N];
nameList = {'初始段','中段','末段'};

for k = 1:length(idxList)
    idx = idxList(k);
    V = Track(idx,4);
    y = Track(idx,3);

    [lin, auto] = Missile_transfer_function_local(V,y,struct());
    canshu = Three_loop_autopilot_local(V,lin,auto);

    point = linear_analysis_one_point_local(V,y);

    points(k).name = nameList{k};
    points(k).pitch = point.pitch;
    points(k).yaw = point.yaw;
    points(k).roll = point.roll;
end

linReport.points = points;
end

function point = linear_analysis_one_point_local(V,y)

[lin, auto] = Missile_transfer_function_local(V,y,struct());

Tm=lin.Tm; zetam=lin.zetam; A2=lin.A2; A1=lin.A1; kdot_upsilon=lin.kdot_upsilon; Tdot_upsilon=lin.Tdot_upsilon;
Tp=lin.Tp; zetap=lin.zetap; A2p=lin.A2p; A1p=lin.A1p; kdot_phi=lin.kdot_phi; Tdot_phi=lin.Tdot_phi;
c_deltax=lin.c_deltax; c_wx=lin.c_wx;

w1=14;zeta1=0.75;tao1=0.2;KACT=-1;c=0;Kac=1;
M0=w1^2/lin.wm^2/tao1;
M1=(tao1+2*zeta1/w1)*M0-1;
M2=(1/w1^2+2*zeta1*tao1/w1)*M0-2*zetam/lin.wm;
juzhen1=[M2;M1;M0];
juzhen3=KACT*kdot_upsilon*[Tdot_upsilon c*Kac*Tdot_upsilon+Kac*V*A2 0;1 c*Kac+Kac*V*A1 Tdot_upsilon;0 Kac*V 1];
juzhen2=inv(juzhen3)*juzhen1;
Kg=juzhen2(1); KA=juzhen2(2); WI=juzhen2(3); KDC=WI/KA/V+Kac;

w2=12;zeta2=0.75;tao2=0.2;KACT=-1;c=0;Kacp=1;
M0p=w2^2/lin.wp^2/tao2;
M1p=(tao2+2*zeta2/w2)*M0p-1;
M2p=(1/w2^2+2*zeta2*tao2/w2)*M0p-2*zetap/lin.wp;
juzhen1p=[M2p;M1p;M0p];
juzhen3p=KACT*kdot_phi*[Tdot_phi c*Kacp*Tdot_phi-Kacp*V*A2p 0;1 c*Kacp-Kacp*V*A1p Tdot_phi;0 -Kacp*V 1];
juzhen2p=inv(juzhen3p)*juzhen1p;
Kgp=juzhen2p(1); KAp=juzhen2p(2); WIp=juzhen2p(3); KDCp=-WIp/KAp/V+Kacp;

w3=14;zeta3=0.7;
Kgama=w3^2/(-KACT*c_deltax);
Kwx=(c_wx-2*zeta3*w3)/(KACT*c_deltax);

% 为了不改变原命中逻辑，线性分析默认不额外引入舵机环节
HG_pitch = tf([M2 M1 M0],[Tm^2 2*Tm*zetam 1 0]);
Gcl_pitch = KDC*KACT*kdot_upsilon*V*KA*tf([A2 A1 1],[Tm^2 2*Tm*zeta1+M2 1+M1 M0]);

HG_yaw = tf([M2p M1p M0p],[Tp^2 2*Tp*zetap 1 0]);
Gcl_yaw = -KDCp*KACT*kdot_phi*V*KAp*tf([A2p A1p 1],[Tp^2 2*Tp*zeta2+M2p 1+M1p M0p]);

HG_roll = tf(-KACT*c_deltax*Kgama,[1 c_wx-KACT*c_deltax*Kwx 0]);
Gcl_roll = tf(-KACT*c_deltax*Kgama,[1 c_wx-KACT*c_deltax*Kwx -KACT*c_deltax*Kgama]);

point.pitch = get_margin_metrics_local(HG_pitch,Gcl_pitch);
point.yaw   = get_margin_metrics_local(HG_yaw,Gcl_yaw);
point.roll  = get_margin_metrics_local(HG_roll,Gcl_roll);
end

function ch = get_margin_metrics_local(Gol,Gcl)
[ch.Gm,ch.Pm,ch.Wcg,ch.Wcp] = margin(Gol);
if isinf(ch.Gm)
    ch.Gm_dB = inf;
else
    ch.Gm_dB = 20*log10(ch.Gm);
end
ch.Pm_deg = ch.Pm;
ch.pole = pole(Gcl);
try
    ch.BW = bandwidth(Gcl);
catch
    ch.BW = NaN;
end
ch.Gol = Gol;
ch.Gcl = Gcl;
end

%% ========================================================================
%% 新增：参数摄动鲁棒性分析
%% ========================================================================
function robustScan = param_robust_scan_local()

scanVec = 0.8:0.05:1.2;

for i = 1:length(scanVec)
    % CLA 摄动
    ps = struct('CLA',scanVec(i),'mza',1.0,'mass',1.0,'push',1.0);
    rpt = linear_analysis_with_param_local(960,7000,ps);
    robustScan.CLA.pm(i) = rpt.pitch.Pm_deg;
    robustScan.CLA.gm(i) = rpt.pitch.Gm_dB;
    robustScan.CLA.bw(i) = rpt.pitch.BW;

    % mza 摄动
    ps = struct('CLA',1.0,'mza',scanVec(i),'mass',1.0,'push',1.0);
    rpt = linear_analysis_with_param_local(960,7000,ps);
    robustScan.mza.pm(i) = rpt.pitch.Pm_deg;
    robustScan.mza.gm(i) = rpt.pitch.Gm_dB;
    robustScan.mza.bw(i) = rpt.pitch.BW;

    % 质量摄动
    ps = struct('CLA',1.0,'mza',1.0,'mass',scanVec(i),'push',1.0);
    rpt = linear_analysis_with_param_local(960,7000,ps);
    robustScan.mass.pm(i) = rpt.pitch.Pm_deg;
    robustScan.mass.gm(i) = rpt.pitch.Gm_dB;
    robustScan.mass.bw(i) = rpt.pitch.BW;

    % 推力摄动
    ps = struct('CLA',1.0,'mza',1.0,'mass',1.0,'push',scanVec(i));
    rpt = linear_analysis_with_param_local(960,7000,ps);
    robustScan.push.pm(i) = rpt.pitch.Pm_deg;
    robustScan.push.gm(i) = rpt.pitch.Gm_dB;
    robustScan.push.bw(i) = rpt.pitch.BW;
end

robustScan.scanVec = scanVec;

fprintf('\n================ 参数摄动鲁棒性分析 ================\n');
fprintf('已完成 CLA / mza / m / P 摄动下的俯仰通道 PM、GM、BW 统计\n');
fprintf('===================================================\n');
end

function rpt = linear_analysis_with_param_local(V,y,paramScale)

[lin,auto] = Missile_transfer_function_local(V,y,paramScale);

Tm=lin.Tm; zetam=lin.zetam; A2=lin.A2; A1=lin.A1; kdot_upsilon=lin.kdot_upsilon; Tdot_upsilon=lin.Tdot_upsilon;
Tp=lin.Tp; zetap=lin.zetap; A2p=lin.A2p; A1p=lin.A1p; kdot_phi=lin.kdot_phi; Tdot_phi=lin.Tdot_phi;
c_deltax=lin.c_deltax; c_wx=lin.c_wx;

w1=14;zeta1=0.75;tao1=0.2;KACT=-1;c=0;Kac=1;
M0=w1^2/lin.wm^2/tao1;
M1=(tao1+2*zeta1/w1)*M0-1;
M2=(1/w1^2+2*zeta1*tao1/w1)*M0-2*zetam/lin.wm;
juzhen1=[M2;M1;M0];
juzhen3=KACT*kdot_upsilon*[Tdot_upsilon c*Kac*Tdot_upsilon+Kac*V*A2 0;1 c*Kac+Kac*V*A1 Tdot_upsilon;0 Kac*V 1];
juzhen2=inv(juzhen3)*juzhen1;
Kg=juzhen2(1); KA=juzhen2(2); WI=juzhen2(3); KDC=WI/KA/V+Kac;

w2=12;zeta2=0.75;tao2=0.2;KACT=-1;c=0;Kacp=1;
M0p=w2^2/lin.wp^2/tao2;
M1p=(tao2+2*zeta2/w2)*M0p-1;
M2p=(1/w2^2+2*zeta2*tao2/w2)*M0p-2*zetap/lin.wp;
juzhen1p=[M2p;M1p;M0p];
juzhen3p=KACT*kdot_phi*[Tdot_phi c*Kacp*Tdot_phi-Kacp*V*A2p 0;1 c*Kacp-Kacp*V*A1p Tdot_phi;0 -Kacp*V 1];
juzhen2p=inv(juzhen3p)*juzhen1p;
Kgp=juzhen2p(1); KAp=juzhen2p(2); WIp=juzhen2p(3); KDCp=-WIp/KAp/V+Kacp;

w3=14;zeta3=0.7;
Kgama=w3^2/(-KACT*c_deltax);
Kwx=(c_wx-2*zeta3*w3)/(KACT*c_deltax);

HG_pitch = tf([M2 M1 M0],[Tm^2 2*Tm*zetam 1 0]);
Gcl_pitch = KDC*KACT*kdot_upsilon*V*KA*tf([A2 A1 1],[Tm^2 2*Tm*zeta1+M2 1+M1 M0]);

HG_yaw = tf([M2p M1p M0p],[Tp^2 2*Tp*zetap 1 0]);
Gcl_yaw = -KDCp*KACT*kdot_phi*V*KAp*tf([A2p A1p 1],[Tp^2 2*Tp*zeta2+M2p 1+M1p M0p]);

HG_roll = tf(-KACT*c_deltax*Kgama,[1 c_wx-KACT*c_deltax*Kwx 0]);
Gcl_roll = tf(-KACT*c_deltax*Kgama,[1 c_wx-KACT*c_deltax*Kwx -KACT*c_deltax*Kgama]);

rpt.pitch = get_margin_metrics_local(HG_pitch,Gcl_pitch);
rpt.yaw   = get_margin_metrics_local(HG_yaw,Gcl_yaw);
rpt.roll  = get_margin_metrics_local(HG_roll,Gcl_roll);
end

%% ========================================================================
%% 画图：保留原程序图
%% ========================================================================
function plot_original_results_local(Track,t)

figure(1);
plot(Track(:,1),Track(:,17),'b-');
xlabel('t'); ylabel('加速度');
hold on
plot(Track(:,1),Track(:,18),'r-');
legend('实际弹体加速度ay','期望弹体加速度ayc');
axis([0 t -200 400]);
hold off

figure(2);
plot(Track(:,1),Track(:,5)*57.3);
xlabel('t'); ylabel('攻角alpha');

figure(3);
plot(Track(:,1),Track(:,6)*57.3);
xlabel('t'); ylabel('俯仰角upsilon');

figure(4);
plot(Track(:,1),Track(:,7)*57.3,Track(:,1),Track(:,22)*57.3);
xlabel('t'); ylabel('角度(°)');
legend('滚转角gama','期望滚转角gamac');

figure(5);
plot(Track(:,1),Track(:,8)*57.3);
xlabel('t'); ylabel('偏航角phi');

figure(6);
plot(Track(:,1),Track(:,4));
xlabel('t'); ylabel('导弹速度V(m/s)');

figure(7);
plot(Track(:,1),Track(:,10)*57.3);
xlabel('时间（s）'); ylabel('角度（°）');
hold on
plot(Track(:,1),Track(:,13)*57.3);
plot(Track(:,1),Track(:,11)*57.3);
legend('舵偏角deltaz','舵偏角deltax','舵偏角deltay');
axis([0 t -20 20]);
hold off

figure(8);
plot(Track(:,1),Track(:,19),'b-');
xlabel('t'); ylabel('加速度');
hold on
plot(Track(:,1),Track(:,20),'r-');
legend('实际弹体加速度az','期望弹体加速度azc');
axis([0 t -400 200]);
hold off

x=Track(:,2);
z=Track(:,12);
y=Track(:,3);
T_x=Track(:,14);
T_y=Track(:,15);
T_z=Track(:,16);
figure(9);
plot3(x,z,y,'b-','LineWidth',1.5);
xlabel('X轴'); ylabel('Z轴'); zlabel('Y轴');
grid on
hold on
plot3(T_x,T_z,T_y,'r-','LineWidth',1.5);
text(x(1), z(1), y(1), '导弹初始点','FontSize',12)
text(x(end), z(end), y(end), '碰撞点','FontSize',12)
text(T_x(1), T_z(1), T_y(1), '目标初始点','FontSize',12)

figure(10);
plot(Track(:,1),Track(:,21)*57.3);
xlabel('t'); ylabel('侧滑角beta');
end

%% ========================================================================
%% 新增：线性分析画图
%% ========================================================================
function plot_linear_results_local(linReport)

for k = 1:length(linReport.points)
    p = linReport.points(k);

    figure;
    margin(p.pitch.Gol);
    title(['俯仰通道开环Bode图 - ', p.name]);

    figure;
    margin(p.yaw.Gol);
    title(['偏航通道开环Bode图 - ', p.name]);

    figure;
    margin(p.roll.Gol);
    title(['滚转通道开环Bode图 - ', p.name]);

    figure;
    pzmap(p.pitch.Gcl); grid on;
    title(['俯仰通道闭环极点图 - ', p.name]);

    figure;
    pzmap(p.yaw.Gcl); grid on;
    title(['偏航通道闭环极点图 - ', p.name]);

    figure;
    pzmap(p.roll.Gcl); grid on;
    title(['滚转通道闭环极点图 - ', p.name]);
end
end

%% ========================================================================
%% 新增：参数摄动分析画图
%% ========================================================================
function plot_param_robust_results_local(robustScan)

x = robustScan.scanVec;

figure;
plot(x,robustScan.CLA.pm,'o-','LineWidth',1.2); hold on;
plot(x,robustScan.mza.pm,'s-','LineWidth',1.2);
plot(x,robustScan.mass.pm,'d-','LineWidth',1.2);
plot(x,robustScan.push.pm,'^-','LineWidth',1.2);
xlabel('参数缩放系数');
ylabel('PM / deg');
legend('CLA','mza','m','P');
title('参数摄动下俯仰通道相位裕度变化');
grid on;

figure;
plot(x,robustScan.CLA.gm,'o-','LineWidth',1.2); hold on;
plot(x,robustScan.mza.gm,'s-','LineWidth',1.2);
plot(x,robustScan.mass.gm,'d-','LineWidth',1.2);
plot(x,robustScan.push.gm,'^-','LineWidth',1.2);
xlabel('参数缩放系数');
ylabel('GM / dB');
legend('CLA','mza','m','P');
title('参数摄动下俯仰通道增益裕度变化');
grid on;

figure;
plot(x,robustScan.CLA.bw,'o-','LineWidth',1.2); hold on;
plot(x,robustScan.mza.bw,'s-','LineWidth',1.2);
plot(x,robustScan.mass.bw,'d-','LineWidth',1.2);
plot(x,robustScan.push.bw,'^-','LineWidth',1.2);
xlabel('参数缩放系数');
ylabel('Bandwidth / rad/s');
legend('CLA','mza','m','P');
title('参数摄动下俯仰通道带宽变化');
grid on;
end

%% ========================================================================
%% 工具函数
%% ========================================================================
function y = sign_nonzero_local(x)
if x >= 0
    y = 1;
else
    y = -1;
end
end

%% ========================================================================
%% RK4
%% ========================================================================
% 四阶龙哥库塔
function XK1 =RK4(XK,dt)  
K1 = dt*dynamics(XK);
K2 = dt*dynamics(XK+K1/2);
K3 = dt*dynamics(XK+K2/2);
K4 = dt*dynamics(XK+K3);
XK1 =XK+(K1+2*K2+2*K3+K4)/6;
end  


%% ========================================================================
%% dynamics
%% ========================================================================
function dXK= dynamics(XK)  
global Jx Jy Jz m S L g P
global Fx_v Fy_v Fz_v
V=XK(1);upsilon=XK(2);gama=XK(3);phi=XK(4);theta=XK(5);phiv=XK(6);
wx=XK(7);
wy=XK(8);wz=XK(9);
x=XK(10);y=XK(11);z=XK(12);
beta=asin(cos(theta)*(cos(gama)*sin(phi-phiv)+sin(upsilon)*sin(gama)*cos(phi-phiv))-sin(theta)*cos(upsilon)*sin(gama));
alpha=asin((cos(theta)*(sin(upsilon)*cos(gama)*cos(phi-phiv)-sin(gama)*sin(phi-phiv))-sin(theta)*cos(upsilon)*cos(gama))/cos(beta));
gamav=asin(1/cos(theta)*(cos(alpha)*sin(beta)*sin(upsilon)-sin(alpha)*sin(beta)*cos(gama)*cos(upsilon)+cos(beta)*sin(gama)*cos(upsilon)));
% 密度rou，发动机沿弹体纵轴推力P（N）。
rou=1.2495*(1-0.0065*y/288.15)^4.25588;
% 动压q
q=0.5*rou*V^2;
% 调取速度坐标系下的气动力系数（阻力、升力、侧向力）、弹体坐标系下的气动力矩系数
coefficient= Areocoefficient(XK);
CD=coefficient(1);CL=coefficient(2);CZ=coefficient(3);
mx=coefficient(4);my=coefficient(5);mz=coefficient(6);
Fx_v =CD*q*S;  %阻力 
Fy_v =CL*q*S;  %升力 
Fz_v =CZ*q*S;  %侧力
Mx = mx*q*S*L; %绕弹体X轴的滚转力矩
My = my*q*S*L; %绕弹体Y轴的滚转力矩
Mz = mz*q*S*L; %绕弹体Z轴的滚转力矩
dv=(P*cos(alpha)*cos(beta)-Fx_v-m*g*sin(theta)) / m;
dtheta=(P*(sin(alpha)*cos(gamav)+cos(alpha)*sin(beta)*sin(gamav))+Fy_v*cos(gamav)-Fz_v*sin(gamav)-m*g*cos(theta)) / (m * V);
dphiv=-1/(m*V*cos(theta))*(P*(sin(alpha)*sin(gamav)-cos(alpha)*sin(beta)*cos(gamav))+Fy_v*sin(gamav)+Fz_v*cos(gamav));
dwx=(Mx-(Jz-Jy)*wy*wz)/Jx;
dwy=(My-(Jx-Jz)*wx*wz)/Jy;
dwz=(Mz-(Jy-Jx)*wy*wx)/Jz;
dx=V*cos(theta)*cos(phiv);
dy=V*sin(theta);
dz=-V*cos(theta)*sin(phiv);
dupsilon=wy*sin(gama)+wz*cos(gama);
dphi=(wy*cos(gama)-wz*sin(gama))/cos(upsilon);
dgama=wx-tan(upsilon)*(wy*cos(gama)-wz*sin(gama));
dXK=[dv,dupsilon,dgama,dphi,dtheta,dphiv,dwx,dwy,dwz,dx,dy,dz];
end  


%% ========================================================================
%% control
%% ========================================================================
function [deltax,deltay,deltaz] =control(XK,Nyc_1,Nzc_1,Nyc_G,Nzc_G,gamac,canshu)  
% 找到的气动力、力矩系数是角度的关系，动导数是无因次化弧度制的关系。注意气动系数度与角度的转换关系，踩坑了。
global dt m Fx_v Fy_v Fz_v
global Ee_az phi_last
global Ee_ay upsilon_last ayc_body ay_body azc_body az_body
V=XK(1);upsilon=XK(2);gama=XK(3);phi=XK(4);theta=XK(5);phiv=XK(6);
wx=XK(7);wy=XK(8);wz=XK(9);
x=XK(10);y=XK(11);z=XK(12);
C45=180/pi;g=9.8;

beta=asin(cos(theta)*(cos(gama)*sin(phi-phiv)+sin(upsilon)*sin(gama)*cos(phi-phiv))-sin(theta)*cos(upsilon)*sin(gama));
alpha=asin((cos(theta)*(sin(upsilon)*cos(gama)*cos(phi-phiv)-sin(gama)*sin(phi-phiv))-sin(theta)*cos(upsilon)*cos(gama))/cos(beta));

trans_vtobody=[cos(alpha)*cos(beta) sin(alpha) -cos(alpha)*sin(beta);-sin(alpha)*cos(beta) cos(alpha) sin(alpha)*sin(beta);sin(beta) 0 cos(beta)];
F_body=trans_vtobody*[-Fx_v;Fy_v;Fz_v]; %在速度坐标系下的气动力，转换至弹体坐标系
Kg=canshu(1);KA=canshu(2);WI=canshu(3);KDC=canshu(4); %俯仰通道回路增益
Kgp=canshu(5);KAp=canshu(6);WIp=canshu(7);KDCp=canshu(8); %偏航通道回路增益
Kgama=canshu(9);Kwx=canshu(10);KACT=canshu(11); %滚转通道回路增益



%% 俯仰通道控制
ay_body=F_body(2)/m;
ayc_G=Nyc_G*g; %重力补偿项
ayc_body=Nyc_1*g+ayc_G; %制导律生成的过载+重力补偿项=送入控制系统输入端的期望过载
e_ay=1*(KDC*ayc_body-ay_body-(KDC-1)*ayc_G);      %在输入端的俯仰过载误差信号
deltaz=KACT*(-WI*upsilon+(Ee_ay+KA*e_ay*dt)-Kg/dt*(upsilon-upsilon_last)); %依据三回路驾驶仪得到的增益，计算舵偏角，参考论文38页框图
Ee_ay=Ee_ay+KA*e_ay*dt;          %误差的累加和
upsilon_last=upsilon;            %前一个误差信号值

%% 偏航通道控制
az_body=F_body(3)/m;
azc_G=Nzc_G*g; %重力补偿项
azc_body=Nzc_1*g+azc_G;
e_az=1*(KDCp*azc_body-az_body-(KDCp-1)*azc_G);      %俯仰过载误差信号
deltay=KACT*(-WIp*phi+(Ee_az+KAp*e_az*dt)-Kgp/dt*(phi-phi_last)); %依据三回路驾驶仪计算的增益，计算舵偏角
deltay=deltay-0.003*wx*ay_body; %偏航通道增加协调支路补偿项，减弱BTT控制过程中各耦合因素造成的误差，具体参考论文55页
Ee_az=Ee_az+KAp*e_az*dt;          %误差的累加和
phi_last=phi;      %前一个误差信号值

%% 滚转通道控制
e_gama=(gamac-gama);      %俯仰过载误差信号
deltax=KACT*(Kgama*e_gama-Kwx*wx); %依据三回路驾驶仪计算的增益


%% 舵机限幅
if abs(deltax)>=15/C45 
    deltax=15*deltax/abs(deltax)/C45;
else 
    deltax=deltax;
end

if abs(deltay)>=15/C45 
    deltay=15*deltay/abs(deltay)/C45;
else 
    deltay=deltay;
end
if abs(deltaz)>=15/C45 
    deltaz=15*deltaz/abs(deltaz)/C45;
else 
    deltaz=deltaz;
end

end

%% ========================================================================
%%  Areocoefficient
%% ========================================================================
function coefficient= Areocoefficient(XK)
% 气动力矩动导数是关于rad无量纲系数,其余系数为无量纲°制。
global beta alpha C45 L
global deltax deltay deltaz
coefficient=zeros(1,11);
V=XK(1);upsilon=XK(2);gama=XK(3);phi=XK(4);theta=XK(5);phiv=XK(6);
wx=XK(7);wy=XK(8);wz=XK(9);
x=XK(10);y=XK(11);z=XK(12);
% 规定角度参与运算都为单位rad，而下文CLA=0.6303等系数是CL关于alpha（°）的斜率，因此后续需要将相关系数都转换为rad制
% 注意：动导数本文给出的是弧度制，不需要转换处理
% 阻力X=CD*q*S=（CD0+CDA*alpha+CDB*beta）*q*S
% 升力Y=CL*q*S=（CL0+CLA*alpha+CLDZ*deltaz）*q*S
% 侧力Z=CZ*q*S=（CZ0+CZB*beta+CZDY*deltay）*q*S
CD0=0.25023;CDA=0.00;CDB=0.00;
CL0=0;CLA=0.6303;CLDZ=0.068651;
CZ0=0.00;CZB=-0.31;CZDY=-0.07921;
mx0=0.0;   mxb=-0.00248;  mxdx=-0.02547;  mxdy=0.001061;
my0=0.00;  myb=-0.19948;  mydy=-0.236;    mydx=0.249;     
mz0=-0.00; mza=-0.06982;  mzdz=-0.21195;

%  动导数，文献给出的是弧度制，不需要转换处理
mxwx=-8;mxwy=0;
mywy=-100;mywx=0;
mzwz=-64;

CD=CD0+CDA*(alpha*C45)^2+CDB*(beta*C45)^2;
CL=CL0+CLDZ*deltaz*C45+CLA*alpha*C45;
CZ=CZ0+CZB*beta*C45+CZDY*deltay*C45;
mx=mx0+mxdx*deltax*C45+mxb*beta*C45+mxdy*deltay*C45+mxwx*wx*L/V+mxwy*wy*L/V; % *L/V是将wx、wy、wz无因次化
my=my0+myb*beta*C45+mydy*deltay*C45+mydx*deltax*C45+mywx*wx*L/V+mywy*wy*L/V;
mz=mz0+mza*alpha*C45+mzdz*deltaz*C45+mzwz*wz*L/V;

coefficient(1)=CD;
coefficient(2)=CL;
coefficient(3)=CZ;
coefficient(4)=mx;
coefficient(5)=my;
coefficient(6)=mz;
coefficient(7)=mxwx;
coefficient(8)=mxwy;
coefficient(9)=mywx;
coefficient(10)=mywy;
coefficient(11)=mzwz;
end

