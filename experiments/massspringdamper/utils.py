"""
Provides functions that are useful across all model architectures.
"""
import datetime
import os
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from tfdiffeq import odeint
from MassSpringDamper import MassSpringDamper

class Lambda(tf.keras.Model):

    def call(self, t, y):
        m = 1
        c = 1
        d = 0
        return tf.stack([y[:, 1], -(d*y[:, 1]+c*y[:, 0]) / m], axis=-1)

class modelFunc(tf.keras.Model):
    """Converts a standard tf.keras.Model to a model compatible with odeint."""

    def __init__(self, model):
        super(modelFunc, self).__init__()
        self.model = model

    def call(self, t, x):
        if len(x.shape) == 1:
            return self.model(tf.expand_dims(x, axis=0))[0]
        return self.model(x)

class RunningAverageMeter():
    """Computes and stores the average and current value"""

    def __init__(self, momentum=0.99):
        self.momentum = momentum
        self.reset()

    def reset(self):
        self.val = None
        self.avg = 0

    def update(self, val):
        if self.val is None:
            self.avg = val
        else:
            self.avg = self.avg * self.momentum + val * (1 - self.momentum)
        self.val = val

def create_dataset(n_series=51, samples_per_series=1001, save_to_disk=True):
    """Creates a dataset with n_series data series that are each simulated for samples_per_series
    time steps. The timesteps are delta_t seconds apart.
    # Arguments:
        n_series: int, number of series to create
        samples_per_series: int, number of samples per series
        save_dataset: bool, whether to save the dataset to disk
    # Returns:
        x_train: np.ndarray, shape=(n_series, samples_per_series, 2)
        y_train: np.ndarray, shape=(n_series, samples_per_series, 2)
        x_val: np.ndarray, shape=(n_series, samples_per_series, 2)
        y_val: np.ndarray, shape=(n_series, samples_per_series, 2)

    """
    delta_t = 0.01
    x0_in = np.random.random((n_series//2))
    x0_out = np.random.random((n_series-n_series//2)) + np.pi - 1
    x0 = np.concatenate([x0_in, x0_out])
    x_train = []
    y_train = []
    for i in range(n_series):
        msd = MassSpringDamper(x=x0[i])
        with tf.device('/gpu:0'):
            x_train.append(msd.step(dt=(samples_per_series-1)*delta_t, n_steps=samples_per_series))
            y_train.append(np.array(msd.call(0., x_train[-1])))
    x_train = np.stack(x_train)
    y_train = np.stack(y_train)

    x_val = []
    y_val = []
    msd = MassSpringDamper(x=5., x_dt=0.5)
    with tf.device('/gpu:0'):
        x_val.append(msd.step(dt=(samples_per_series-1)*delta_t, n_steps=samples_per_series))
        y_val.append(np.array([msd.call(0., x_val[-1])]))
    msd = MassSpringDamper(x=1.5, x_dt=0.5)
    with tf.device('/gpu:0'):
        x_val.append(msd.step(dt=(samples_per_series-1)*delta_t, n_steps=samples_per_series))
        y_val.append(np.array([msd.call(0., x_val[-1])]))
    x_val = np.stack(x_val)
    y_val = np.stack(y_val)

    if save_to_disk:
        np.save('experiments/datasets/mass_spring_damper_x_train.npy', x_train)
        np.save('experiments/datasets/mass_spring_damper_y_train.npy', y_train)
        np.save('experiments/datasets/mass_spring_damper_x_val.npy', x_val)
        np.save('experiments/datasets/mass_spring_damper_y_val.npy', y_val)
    return x_train, y_train, x_val, y_val

def load_dataset():
    x_train = np.load('experiments/datasets/mass_spring_damper_x_train.npy').astype(np.float32)
    y_train = np.load('experiments/datasets/mass_spring_damper_y_train.npy').astype(np.float32)
    x_val = np.load('experiments/datasets/mass_spring_damper_x_val.npy').astype(np.float32)
    y_val = np.load('experiments/datasets/mass_spring_damper_y_val.npy').astype(np.float32)
    return x_train, y_train, x_val, y_val


def makedirs(dirname):
    if not os.path.exists(dirname):
        os.makedirs(dirname)


def total_energy(state, k=1, m=1):
    """Calculates total energy of a mass-spring-damper system given a state."""
    if len(state.shape) == 1:
        return 0.5*k*state[0]*state[0]+0.5*m*state[1]*state[1]
    if len(state.shape) == 2:
        return 0.5*k*state[:, 0]*state[:, 0]+0.5*m*state[:, 1]*state[:, 1]
    raise ValueError('NDIM must be 1 or 2 but is {}'.format(len(state.shape)))


def relative_energy_drift(x_pred, x_true, t=-1):
    """Computes the relative energy drift of x_pred w.r.t. x_true
    # Arguments:
        x_pred: numpy.ndarray shape=(n_datapoints, 2) - predicted time series
        x_true: numpy.ndarray shape=(n_datapoints, 2) - reference time series
        t: int, index at which to compute the energy drift, (default: -1)
    """
    energy_pred = total_energy(x_pred[t])
    energy_true = total_energy(x_true[t])
    return (energy_pred-energy_true) / energy_true


def relative_phase_error(x_pred, x_val):
    """Computes the relative phase error of x_pred w.r.t. x_true.
    This is done by finding the locations of the zero crossings in both signals,
    then corresponding crossings are compared to each other.

    # Arguments:
        x_pred: numpy.ndarray shape=(n_datapoints, 2) - predicted time series
        x_true: numpy.ndarray shape=(n_datapoints, 2) - reference time series
    """
    ref_crossings = zero_crossings(x_val[:, 0])
    pred_crossings = zero_crossings(x_pred[:, 0])
    n_crossings = min(len(pred_crossings), len(ref_crossings))
    phase_error = 1 / ref_crossings[:n_crossings]-1 / pred_crossings[:n_crossings]
    return np.mean(phase_error * ref_crossings[:n_crossings])


def trajectory_error(x_pred, x_val):
    return np.mean(np.abs(x_pred - x_val))


def visualize(model, x_val, PLOT_DIR, TIME_OF_RUN, args, ode_model=True, latent=False, epoch=0):
    """Visualize a tf.keras.Model for a single pendulum.
    # Arguments:
        model: A Keras model, that accepts t and x when called
        x_val: np.ndarray, shape=(1, samples_per_series, 2) or (samples_per_series, 2)
                The reference time series, against which the model will be compared
        PLOT_DIR: Directory to plot in
        TIME_OF_RUN: Time at which the run began
        ode_model: whether the model outputs the derivative of the current step (True),
                   or the value of the next step (False)
        args: input arguments from main script
    """
    x_val = x_val.reshape(2, -1, 2)
    dt = 0.01
    t = tf.linspace(0., 10., int(10./dt)+1)
    # Compute the predicted trajectories
    if ode_model:
        if latent: # NODE-e2e model
            x0_extrap = tf.stack([x_val[0, 0]])
            x_t_extrap = odeint(model, x0_extrap, t, rtol=1e-5, atol=1e-5).numpy()[:, 0]
            x0_interp = tf.stack([x_val[1, 0]])
            x_t_interp = odeint(model, x0_interp, t, rtol=1e-5, atol=1e-5).numpy()[:, 0]
        else:  # regular (Dense or NODE-Net) model
            x0_extrap = tf.stack(x_val[0, 0])
            x_t_extrap = odeint(model, x0_extrap, t, rtol=1e-5, atol=1e-5).numpy()
            x0_interp = tf.stack(x_val[1, 0])
            x_t_interp = odeint(model, x0_interp, t, rtol=1e-5, atol=1e-5).numpy()
    else: # LSTM model
        x_t_extrap = np.zeros((1001, 2))
        x_t_extrap[0] = x_val[0, 0]
        x_t_interp = np.zeros((1001, 2))
        x_t_interp[0] = x_val[1, 0]
        # Always injects the entire time series because keras is slow when using
        # varying series lengths and the future timesteps don't affect the predictions
        # before it anyways.
        for i in range(1, len(t)):
            x_t_extrap[i:i+1] = model(0., np.expand_dims(x_t_extrap, axis=0))[0, i-1:i]
        for i in range(1, len(t)):
            x_t_interp[i:i+1] = model(0., np.expand_dims(x_t_interp, axis=0))[0, i-1:i]

    x_t = np.stack([x_t_extrap, x_t_interp], axis=0)
    # Plot the generated trajectories
    fig = plt.figure(figsize=(12, 8), facecolor='white')
    ax_traj = fig.add_subplot(231, frameon=False)
    ax_phase = fig.add_subplot(232, frameon=False)
    ax_vecfield = fig.add_subplot(233, frameon=False)
    ax_vec_error_abs = fig.add_subplot(234, frameon=False)
    ax_vec_error_rel = fig.add_subplot(235, frameon=False)
    ax_energy = fig.add_subplot(236, frameon=False)
    ax_traj.cla()
    ax_traj.set_title('Trajectories')
    ax_traj.set_xlabel('t')
    ax_traj.set_ylabel('x,y')
    ax_traj.plot(t.numpy(), x_val[0, :, 0], t.numpy(), x_val[0, :, 1], 'g-')
    ax_traj.plot(t.numpy(), x_t[0, :, 0], '--', t.numpy(), x_t[0, :, 1], 'b--')
    ax_traj.set_xlim(min(t.numpy()), max(t.numpy()))
    ax_traj.set_ylim(-6, 6)
    ax_traj.legend()

    ax_phase.cla()
    ax_phase.set_title('Phase Portrait')
    ax_phase.set_xlabel('x')
    ax_phase.set_ylabel('x_dt')
    ax_phase.plot(x_val[0, :, 0], x_val[0, :, 1], 'g--')
    ax_phase.plot(x_t[0, :, 0], x_t[0, :, 1], 'b--')
    ax_phase.plot(x_val[1, :, 0], x_val[1, :, 1], 'g--')
    ax_phase.plot(x_t[1, :, 0], x_t[1, :, 1], 'b--')
    ax_phase.set_xlim(-6, 6)
    ax_phase.set_ylim(-6, 6)

    ax_vecfield.cla()
    ax_vecfield.set_title('Learned Vector Field')
    ax_vecfield.set_xlabel('x')
    ax_vecfield.set_ylabel('x_dt')

    steps = 61
    y, x = np.mgrid[-6:6:complex(0, steps), -6:6:complex(0, steps)]
    ref_func = Lambda()
    dydt_ref = ref_func(0., tf.convert_to_tensor(np.stack([x, y], -1).reshape(steps * steps, 2))).numpy()
    mag_ref = 1e-8+np.sqrt(dydt_ref[:, 0]**2 + dydt_ref[:, 1]**2).reshape(-1, 1)
    dydt_ref = dydt_ref.reshape(steps, steps, 2)
    if ode_model:
        dydt = model(0., tf.convert_to_tensor(np.stack([x, y], -1).reshape(steps * steps, 2))).numpy()
    else:
        # Compute artificial x_dot by numerically diffentiating:
        # x_dot \approx (x_{t+1}-x_t)/dt
        yt_1 = model(0., np.stack([x, y], -1).reshape(steps * steps, 1, 2))[:, 0]
        dydt = (np.array(yt_1)-np.stack([x, y], -1).reshape(steps * steps, 2)) / dt

    abs_dydt = dydt.reshape(steps, steps, 2)
    mag = np.sqrt(dydt[:, 0]**2 + dydt[:, 1]**2).reshape(-1, 1)
    dydt = (dydt / mag) # make unit vector
    dydt = dydt.reshape(steps, steps, 2)

    ax_vecfield.streamplot(x, y, dydt[:, :, 0], dydt[:, :, 1], color="black")
    ax_vecfield.set_xlim(-6, 6)
    ax_vecfield.set_ylim(-6, 6)

    ax_vec_error_abs.cla()
    ax_vec_error_abs.set_title('Abs. error of xdot')
    ax_vec_error_abs.set_xlabel('x')
    ax_vec_error_abs.set_ylabel('x_dt')

    x_dif = abs_dydt[:, :, 0]-dydt_ref[:, :, 0]
    y_dif = abs_dydt[:, :, 1]-dydt_ref[:, :, 1]
    abs_dif = np.clip(np.sqrt(x_dif**2 + y_dif**2), 0., 3.)
    c1 = ax_vec_error_abs.contourf(x, y, abs_dif, 100)
    plt.colorbar(c1, ax=ax_vec_error_abs)

    ax_vec_error_abs.set_xlim(-6, 6)
    ax_vec_error_abs.set_ylim(-6, 6)


    ax_vec_error_rel.cla()
    ax_vec_error_rel.set_title('Rel. error of xdot')
    ax_vec_error_rel.set_xlabel('x')
    ax_vec_error_rel.set_ylabel('x_dt')

    rel_dif = np.clip(abs_dif / mag_ref.reshape(steps, steps), 0., 1.)
    c2 = ax_vec_error_rel.contourf(x, y, rel_dif, 100)
    plt.colorbar(c2, ax=ax_vec_error_rel)

    ax_vec_error_rel.set_xlim(-6, 6)
    ax_vec_error_rel.set_ylim(-6, 6)

    ax_energy.cla()
    ax_energy.set_title('Total Energy')
    ax_energy.set_xlabel('t')
    ax_energy.plot(np.arange(1001)/100.1, np.array([total_energy(x_) for x_ in x_t_interp]))
    fig.tight_layout()
    plt.savefig(PLOT_DIR + '/{:03d}'.format(epoch))
    plt.close()

    # Compute Metrics
    energy_drift_extrap = relative_energy_drift(x_t[0], x_val[0])
    phase_error_extrap = relative_phase_error(x_t[0], x_val[0])
    traj_error_extrap = trajectory_error(x_t[0], x_val[0])

    energy_drift_interp = relative_energy_drift(x_t[1], x_val[1])
    phase_error_interp = relative_phase_error(x_t[1], x_val[1])
    traj_error_interp = trajectory_error(x_t[1], x_val[1])


    wall_time = (datetime.datetime.now()
                 - datetime.datetime.strptime(TIME_OF_RUN, "%Y%m%d-%H%M%S")).total_seconds()
    string = "{},{},{},{},{},{},{},{}\n".format(wall_time, epoch,
                                                energy_drift_interp, energy_drift_extrap,
                                                phase_error_interp, phase_error_extrap,
                                                traj_error_interp, traj_error_extrap)
    file_path = (PLOT_DIR + TIME_OF_RUN + "results"
                 + str(args.lr) + str(args.dataset_size) + str(args.batch_size)
                 + ".csv")
    if not os.path.isfile(file_path):
        title_string = ("wall_time,epoch,energy_drift_interp,energy_drift_extrap, phase_error_interp,"
                        + "phase_error_extrap, traj_err_interp, traj_err_extrap\n")
        fd = open(file_path, 'a')
        fd.write(title_string)
        fd.close()
    fd = open(file_path, 'a')
    fd.write(string)
    fd.close()

def zero_crossings(x):
    """Find indices of zeros crossings"""
    return np.array(np.where(np.diff(np.sign(x)))[0])
