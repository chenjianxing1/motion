import numpy as np
from .utils import find_precs, find_mus
import scipy.sparse as sp
import matplotlib.pyplot as plt
import scipy

class SLSBase(object):
    def __init__(self, x_dim, u_dim, N, dtype=np.float64):
        """
        Base class for SLS module.
        Sets the dynamics model and the cost function.
        """
        self.N = N
        self.x_dim = x_dim
        self.u_dim = u_dim
        self.A = None
        self.B = None
        self.dtype = dtype

        self._Q = None
        self._xd = None
        self._R = None
        self._ud = None

        self.C = np.kron(np.triu(np.ones((N, N), dtype=dtype)).T, np.eye(x_dim, dtype=dtype))
        self.D = np.zeros((x_dim*N,N*u_dim ), dtype=dtype)
        self.PHI_U = np.zeros((self.N * self.u_dim, self.N * self.x_dim), dtype=dtype)

        self.du = None
        self.dx = None
        self.PHI_X = None
        self.l_side_invs = None

        bad_rows = np.arange(0, u_dim).tolist()
        bad_cols = np.arange(0, u_dim).tolist()

        # Below is the code to take the inverses in a fast way by 1-rank reduction techniques.
        def invert_k_rank_down(A, A_inv):
            good_rows = np.setdiff1d(np.arange(A.shape[0]), bad_rows)
            good_cols = np.setdiff1d(np.arange(A.shape[1]), bad_cols)
            U = np.zeros((A.shape[0], 2 * u_dim))
            U[bad_rows, :u_dim] = np.eye(u_dim)
            U[good_rows, u_dim:] = A[np.ix_(good_rows, bad_cols)]

            V = np.zeros((2 * u_dim, A.shape[1]))
            V[:u_dim, good_cols] = A[np.ix_(bad_rows, good_cols)]
            V[u_dim:, bad_cols] = np.eye(u_dim)
            return (A_inv + A_inv @ U @ np.linalg.inv(np.eye(V.shape[0]) - V @ A_inv @ U) @ V @ A_inv)[u_dim:, u_dim:]

        def compute_inverses(A):
            A_ = A.copy()
            A_inv_ = np.linalg.inv(A_)
            A_invs2 = [A_inv_]
            for i in range(self.N):
                A_invs2 += [invert_k_rank_down(A[i * u_dim:, i * u_dim:], A_invs2[i])]
            return A_invs2

        self.invert_k_rank_down = invert_k_rank_down
        self.compute_inverses = compute_inverses


    def set_cost_variables(self, zs, Qs, seq, u_std):
        self.l_side_invs = None # resetting inverses
        self.zs = zs
        self.Qs = Qs
        self.seq = seq
        self.Rt = np.eye(self.u_dim) * u_std
        self.Q = find_precs(Qs, seq, sqrt=False).astype(self.dtype)
        self.xd = find_mus(zs, seq).astype(self.dtype)
        self.R = sp.csc_matrix(sp.block_diag([sp.eye(self.u_dim) * u_std] * self.N)).astype(self.dtype)


    def compute_cost(self, x, u=None, cost_function=None):
        if cost_function is None:
            if len(x.shape) == 3: # batch solutions
                x = x.reshape(x.shape[0], -1)
            else:
                x = x.reshape(1, -1)
            dx = x - self.xd
            cost_ = np.sum(dx * (self.Q @ dx.T).T, axis=-1)
            if u is not None:
                if len(u.shape) == 3:
                    u = u.reshape(u.shape[0], -1)
                else:
                    u = u.reshape(1, -1)
                cost_ += np.sum(u * (self.R @ u.T).T, axis=-1)
            if cost_.shape[0] == 1:
                return cost_[0]
            else:
                return cost_
        else:
            return cost_function(x=x, u=u)

    @property
    def AB(self):
        """
        Returns: A list of A and B matrices
        """
        return [self.A, self.B]

    @AB.setter
    def AB(self, value):
        """
        Sets or updates the values of A, B, C and D matrices. We define $C = (I-ZA_d)^{-1}$ and $D = CZB_d$
        Args:
            value: a list of A and B [A,B]
        """
        self.A, self.B = value[0], value[1]
        for i in range(self.N - 1, 0, -1):
            self.D[i * self.x_dim:, (i - 1) * self.u_dim:i * self.u_dim] = \
                self.C[i * self.x_dim:, i * self.x_dim:(i + 1) * self.x_dim] @ self.B

            self.C[i * self.x_dim:, (i - 1) * self.x_dim:i * self.x_dim] = \
                self.C[i * self.x_dim:, i * self.x_dim:(i + 1) * self.x_dim] @ self.A


    def forward_model(self, x, u):
        if x.ndim >= 2:
            return x.dot(self.A.T) + u.dot(self.B.T)
        else:
            return self.A.dot(x) + self.B.dot(u)

    #################################### AT OPTIMALITY, RUN THESE ################################
    def u_optimal(self, x0, PHI_U, du):
        return (PHI_U[:,:self.x_dim] @ x0 + du).reshape(self.N, -1)[:-1]

    def x_optimal(self, x0, PHI_X, dx):
        return (PHI_X[:, :self.x_dim] @ x0 + dx).reshape(self.N, -1)

    def get_trajectory_batch(self, x0, us):
        pass

    def get_trajectory_dp(self, x0, K, k, noise_scale=0):
        batch_size = x0.shape[0] if x0.ndim == 2 else 1
        u_log = np.zeros((batch_size, self.N, self.u_dim))
        x_log = np.zeros((batch_size, self.N+1, self.x_dim))
        x_log[:, 0] = x0
        for i in range(self.N):
            u_log[:, i] = x_log[:, i].dot(K[i].T) + k[i]
            w = np.random.normal(loc=0, scale=noise_scale, size=x0.shape)
            x_log[:, i+1] = self.forward_model(x_log[:, i], u_log[:, i]) + w
        if batch_size == 0:
            print(x_log.shape, u_log.shape)
            return x_log[0, :-1], u_log[0]
        else:
            return x_log[:, :-1], u_log

    def get_trajectory_sls(self, x0, K, k, noise_scale=0):
        batch_size = x0.shape[0] if x0.ndim == 2 else 0
        u_log = np.zeros((batch_size, self.N, self.u_dim))
        x_log = np.zeros((batch_size, self.N+1, self.x_dim))
        x_log[:, 0] = x0
        x_vec = np.zeros((batch_size, self.N * self.x_dim))
        for i in range(self.N):
            x_vec[:, i * self.x_dim:(i + 1) * self.x_dim] = x_log[:, i]
            u_log[:, i] = (x_vec @ K.T + k)[:, i * self.u_dim:(i + 1) * self.u_dim]
            w = np.random.normal(loc=0, scale=noise_scale, size=x0.shape)
            x_log[:, i+1] = self.forward_model(x_log[:, i], u_log[:, i]) + w
        if batch_size == 0:
            return x_log[0, :-1], u_log[0]
        else:
            return x_log[:, :-1], u_log

    def compute_Rr_Qr(self, rho_x, rho_u, dp=True):
        if rho_x is None:
            Qr = None
        else:
            if type(rho_x) == float or type(rho_x) == int:
                Qr = np.tile(rho_x * np.eye(self.x_dim)[None], (self.N, 1, 1))
            elif rho_x.shape[0] == self.x_dim:
                Qr = np.zeros((self.N, self.d, self.d))
                Qr[:] = rho_x
            else:
                Qr = rho_x
            if not dp:
                Qr = scipy.linalg.block_diag(*Qr)
        if rho_u is None:
            Rr = None
        else:
            if type(rho_u) == float or type(rho_x) == int:
                Rr = [rho_u * np.eye(self.u_dim)]*self.N
            elif rho_u.shape[0] == self.u_dim:
                Rr = [rho_u] * self.N
            else:
                Rr = rho_u
            if not dp:
                Rr = scipy.linalg.block_diag(*Rr)
        return Qr, Rr

    ##################################### Setters and Getters #####################################

    @property
    def Q(self):
        return self._Q

    @Q.setter
    def Q(self, value):
        self._Q = value

    @property
    def R(self):
        return self._R

    @R.setter
    def R(self, value):
        self._R = value

    @property
    def xd(self):
        return self._xd

    @xd.setter
    def xd(self, value):
        self._xd = value

    @property
    def ud(self):
        return self._ud

    @ud.setter
    def ud(self, value):
        self._ud = value

    ################################ RESETTING THE SOLUTION #######################################################
    def reset(self):
        self.PHI_U = np.zeros((self.N * self.u_dim, self.N * self.x_dim))
        self.PHI_X = None
        self.du = None
        self.dx = None


    ############################################### PLOTTING ################################################
    def plot_phi_x(self):
        fig, ax = plt.subplots(ncols=2, figsize=(10, 5), sharey=True, sharex=True)
        resultant = np.array([np.abs(self.PHI_X), np.abs(self.PHI_X2)])
        min_val, max_val = np.amin(resultant), np.amax(resultant)
        ax[0].imshow(np.abs(self.PHI_X), vmin=min_val, vmax=max_val)
        ax[1].imshow(np.abs(self.PHI_X2), vmin=min_val, vmax=max_val)

    def plot_phi_u(self):
        fig, ax = plt.subplots(ncols=2, figsize=(10, 5), sharey=True, sharex=True)
        resultant = np.array([np.abs(self.PHI_U), np.abs(self.PHI_U2)])
        min_val, max_val = np.amin(resultant), np.amax(resultant)
        ax[0].imshow(np.abs(self.PHI_U), vmin=min_val, vmax=max_val)
        ax[1].imshow(np.abs(self.PHI_U2), vmin=min_val, vmax=max_val)
