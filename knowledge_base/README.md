# MATLAB Knowledge Base

MATLAB scripts for guidance system simulation and robust analysis.

## Directory Structure

```
knowledge_base/
└── matlab/
    ├── guidance/                    # Guidance system simulation
    │   ├── guidance_simulation.m    # Basic guidance simulation
    │   └── optimize_guidance.m    # GA-based optimization
    └── robust_analysis/             # Robustness analysis
        └── chengxu_robust_analysis_singlefile.m  # Comprehensive robust analysis
```

## Scripts

### guidance_simulation.m
Basic proportional navigation guidance simulation with:
- Navigation coefficient optimization
- Damping ratio control
- Miss distance and control energy metrics

### optimize_guidance.m
Genetic algorithm based parameter optimization for guidance system.

### chengxu_robust_analysis_singlefile.m
Comprehensive missile guidance robustness analysis including:
- Time-domain performance metrics
- Multi-point linear robustness analysis (PM, GM, BW)
- Parameter perturbation analysis (CLA, mza, mass, thrust)
- 3D trajectory visualization
- Autopilot design (three-loop)
