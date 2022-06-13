# iLQR-ADMM
Constrained robust optimal control library for robotics.

**Robust (SLS-ADMM) and non-robust (LQT-ADMM) optimal control with state and control constraints
for a double integrator system**
* SLS-ADMM can guarantee robustness to an initial position change within a given variance, 
with a chosen safety probability, while LQT-ADMM only satisfies the constraints along the nominal solution.
![Robust](images/robust.png)

**iLQR-ADMM with state and control bounds for a 3DoF planar robot arm.**
* Fast optimization for nonlinear systems
![3DoF Robot](images/3dof.png)

**iLQR with control bounds for a 2D car model.**
* Fast optimization for nonlinear systems
<img src="https://github.com/hgirgin/iLQR-ADMM/images/animation.gif" width="40" height="40" />



Dependencies:
- numpy
- scipy
- matplotlib
- pinocchio