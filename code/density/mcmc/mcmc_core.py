import emcee, corner, sys, random, os, warnings
import numpy as np
from scipy.linalg import pinvh
from multiprocessing import Pool, Lock
sys.path.append("..")
from core import Asteroid, UncertaintyTracker
from scipy.optimize import minimize
from threading import Thread
from display import make_gif, make_slices

N_WALKERS = 32
MAX_L = 3
N_FITTED_MOMENTS = 9
N_CONSTRAINED = 7
MAX_N_STEPS = 100_000

MAX_DENSITY = 3 # Iron
MIN_DENSITY = 0.25

NUM_THREADS = os.cpu_count()
MIN_LOG_LIKE = 1000
MINIMIZATION_ATTEMPTS = 500
EPSILON = 1e-10
MINIMUM_LIKELIHOOD = -1000
NUM_SUCCESSES = 1

class MCMCMethod:
    def __init__(self, asteroid, mean_density, n_free, n_all, generate):
        self.mean_density = mean_density
        self.n_free = n_free
        self.n_all = n_all
        self.set_up(asteroid, generate)

    def set_up(self, asteroid, generate):
        raise NotImplementedError()

    def short_name(self):
        raise NotImplementedError()

    def get_theta_long(self, theta_short):
        raise NotImplementedError()

    def pick_parameters(self, local_rng):
        raise NotImplementedError()

    def log_prior(self, theta_long):
        raise NotImplementedError()

    def get_klms(self, theta_long):
        raise NotImplementedError()

    def scatter_walkers(self, theta_start, n_walkers):
        raise NotImplementedError()

class MinResult:
    def __init__(self):
        self.lock = Lock()
        self.x = None
        self.y = None
        self.attempts = 0
        self.successes = 0
    
    def set(self, x, y):
        self.lock.acquire()
        if self.x is None or y < self.y:
            self.y = y
            self.x = x
        self.successes += 1
        self.lock.release()

    def increment(self):
        self.lock.acquire()
        self.attempts += 1
        self.lock.release()

    def query_exceeded_attempts(self, threshold):
        self.lock.acquire()
        greater = self.attempts > threshold
        self.lock.release()
        return greater

    def get_value(self):
        self.lock.acquire()
        v = self.x, self.y
        self.lock.release()
        return v

    def is_satisfied(self):
        self.lock.acquire()
        result = self.successes >= NUM_SUCCESSES
        self.lock.release()
        return result

class CompletedException(Exception):
    pass

class DataStorage:
    def __init__(self, sample_path, surface_am, bulk_am):
        with open(sample_path, 'rb') as f:
            data = np.load(f).reshape(-1, N_FITTED_MOMENTS + 1)
            initial_rolls = data[:, 0]
            flat_samples = data[:, 1:]
        if flat_samples.shape[0] == 0:
            self.data = None
            self.data_inv_covs = None
            return
        complex_samples = np.zeros((len(flat_samples), 6), dtype=np.complex)
        complex_samples[:, 0] = flat_samples[:, 0] # K22
        complex_samples[:, 1] = flat_samples[:, 1] # K20
        complex_samples[:, 2] = flat_samples[:, 2] + 1j * flat_samples[:, 3] # K33
        complex_samples[:, 3] = flat_samples[:, 4] + 1j * flat_samples[:, 5] # K32
        complex_samples[:, 4] = flat_samples[:, 6] + 1j * flat_samples[:, 7] # K31
        complex_samples[:, 5] = flat_samples[:, 8] # K30
        ms = np.array([
            0, # I chose not to apply to K22 because the correction is so small
            0, 3, 2, 1, 0])
        exponents = -1j * np.outer(initial_rolls - np.mean(initial_rolls), ms)
        complex_hybrid_samples = complex_samples * np.exp(exponents)
        real_hybrid_samples = np.zeros_like(flat_samples)

        real_hybrid_samples[:, 0]  = complex_hybrid_samples[:, 0].real # K22
        real_hybrid_samples[:, 1]  = complex_hybrid_samples[:, 1].real # K20
        real_hybrid_samples[:, 2]  = complex_hybrid_samples[:, 2].real * (bulk_am / surface_am) # R K33
        real_hybrid_samples[:, 3]  = complex_hybrid_samples[:, 2].imag * (bulk_am / surface_am) # I K33
        real_hybrid_samples[:, 4]  = complex_hybrid_samples[:, 3].real * (bulk_am / surface_am) # R K32
        real_hybrid_samples[:, 5]  = complex_hybrid_samples[:, 3].imag * (bulk_am / surface_am) # I K32
        real_hybrid_samples[:, 6]  = complex_hybrid_samples[:, 4].real * (bulk_am / surface_am) # R K31
        real_hybrid_samples[:, 7]  = complex_hybrid_samples[:, 4].imag * (bulk_am / surface_am) # I K31
        real_hybrid_samples[:, 8]  = complex_hybrid_samples[:, 5].real * (bulk_am / surface_am) # R K30

        cov = np.cov(real_hybrid_samples.transpose())
        part_cov = cov[2:,2:]
        self.data = np.mean(real_hybrid_samples, axis=0)

        if cov is None:
            # Sample path was empty
            return False
        self.data_inv_covs = pinvh(cov)
        self.data_part_inv_covs = pinvh(part_cov)

def log_probability(theta_short, method, data_storage):
    theta_long = method.get_theta_long(theta_short)
    free_klms = method.get_klms(theta_long)[:N_FITTED_MOMENTS]
    lp = method.log_prior(theta_long)
    ll = log_like(free_klms, data_storage)
    return ll + lp

def log_like(free_klms, data_storage):
    diff_klms = free_klms - data_storage.data # Only need the unconstrained ones
    return -0.5 * diff_klms.transpose() @ data_storage.data_inv_covs @ diff_klms


class MCMCAsteroid:
    def __init__(self, name, sample_path, indicator, shape, surface_am, division, max_radius, dof, used_bulk_am, true_moments=None):
        if used_bulk_am is None:
            used_bulk_am = surface_am
        self.name = name
        self.asteroid = Asteroid(name, surface_am, division, max_radius, indicator, shape, true_moments)
        self.asteroid.max_l = MAX_L
        self.mean_density = 1 / (np.sum(self.asteroid.indicator_map) * division**3)
        self.data_storage = DataStorage(sample_path, surface_am, used_bulk_am)
        self.n_free = dof
        self.n_all = dof + N_CONSTRAINED

        
    def pipeline(self, method_class, make_map, generate=True, n_samples=None, unc_tracker_file=None, cut_k2m=False):
        if n_samples is None and make_map:
            raise Exception("Number of samples cannot be none if make_map is true")

        if self.data_storage.data is None:
            return None

        if unc_tracker_file is None:        
            method = method_class(self.asteroid, self.mean_density, self.n_free, self.n_all, generate)

            long_samples = self.get_densities_mcmc(method, generate)
            if long_samples is None:
                return None

            unc_tracker = UncertaintyTracker()
            if n_samples is not None:
                print(f"Generating {n_samples} samples")
                for i in range(n_samples):
                    # Pull random MCMC sample
                    sample = long_samples[np.random.randint(0, len(long_samples))]
                    # Extract the associated density distro
                    densities = method.get_map(sample, None, self.asteroid)
                    densities /= np.nansum(densities)
                    # Add it to the uncertainty tracker
                    unc_tracker.update(densities)
        else:
            with open(unc_tracker_file, 'rb') as f:
                unc_tracker = UncertaintyTracker.load(f)

        if make_map:
            densities, uncertainty = unc_tracker.generate()
            if densities is None:
                raise Exception("No samples were found in the unc tracker")
            uncertainty_ratios = uncertainty / densities
            true_densities = self.asteroid.get_true_densities().astype(float)
            true_densities[~self.asteroid.indicator_map] = np.nan


            zero_densities = densities.copy()
            zero_densities[np.isnan(densities)] = 0
            
            moment_field = self.asteroid.moment_field(self.asteroid.surface_am)

            # Calculate klm
            unscaled_klm = np.einsum("iabc,abc->i", moment_field, zero_densities) * self.asteroid.division**3
            radius_sqr = unscaled_klm[-1].real
            klms = unscaled_klm / radius_sqr
            klms[0] *= radius_sqr

            # Find likelihood
            free_real_klms = np.array([
                klms[4].real, # K22
                klms[6].real, # K20
                klms[15].real, # R K33
                klms[15].imag, # I K33
                klms[14].real, # R K32
                klms[14].imag, # I K32
                klms[13].real, # R K31
                klms[13].imag, # I K31
                klms[12].real, # K30
            ])

            diff_klms_part = free_real_klms[2:] - self.data_storage.data[2:]
            error_part = diff_klms_part.transpose() @ self.data_storage.data_part_inv_covs @ diff_klms_part / self.n_free

            likelihood_full = log_like(free_real_klms, self.data_storage)
            error_full = -2 * likelihood_full / self.n_free

            print("Real klms:", free_real_klms)
            print("Data klms:", self.data_storage.data)
            print("Redchi full", error_full)
            print("Redchi K3m", error_part)

            error = error_part if cut_k2m else error_full

            self.display(densities, true_densities, uncertainty_ratios, error)

        return unc_tracker

    
    def get_densities_mcmc(self, method, generate):
        output_name = self.name + "-" + method.short_name()
        if generate:
            theta_start = self.get_theta_start_mcmc(method)
            if theta_start is None:
                print("Bailed")
                return None
            sampler = self.mcmc_fit(theta_start, output_name, method, True)
            if sampler is None:
                return None

            try:
                tau = sampler.get_autocorr_time()
            except Exception:
                tau = None
            if tau is not None:
                max_tau = int(np.max(tau))
                samples = sampler.get_chain(discard=2 * max_tau, thin=max_tau // 2)
            else:
                print("No convergence")
                samples = sampler.get_chain(discard=1000, thin=32)
            sample_mask = sampler.get_last_sample().log_prob > MINIMUM_LIKELIHOOD
            print(f"Using {np.sum(sample_mask)}/{N_WALKERS} walkers")
            flat_samples = samples[:,sample_mask,:].reshape(-1, self.n_free)
            long_samples = np.array([method.get_theta_long(theta_short) for theta_short in flat_samples])

            with open(output_name + ".npy", 'wb') as f:
                np.save(f, long_samples)
        
        else:
            with open(output_name + ".npy", 'rb') as f:
                long_samples = np.load(f)


        # Plot corner plot
        long_means, _ = self.get_stats_from_long_samples(long_samples)
        dyn_range = []
        for i in range(len(long_means)):
            min_val, max_val = np.nanpercentile(long_means[i], 5), np.nanpercentile(long_means[i], 95)
            if min_val == max_val:
                min_val -= 1
                max_val += 1
            dyn_range.append((min_val, max_val))

        sys.stderr = open(os.devnull, "w")  # silence stderr
        fig = corner.corner(long_samples, range=dyn_range)
        corner.overplot_lines(fig, long_means, color='C1')
        fig.savefig(output_name + ".png")
        sys.stderr = sys.__stderr__  # unsilence stderr

        return long_samples


    def get_stats_from_long_samples(self, long_samples):
        short_samples = long_samples[:, :self.n_free]

        # Don't compute the mean; compute the middle of the data set.
        least_dist = None
        for i, point in enumerate(short_samples):
            mean_dist = np.sum((short_samples - point)**2) / len(short_samples)
            if least_dist is None or least_dist > mean_dist:
                least_dist = mean_dist
                least_point_index = i
        
        long_means = long_samples[least_point_index]
        high_unc = np.percentile(long_samples, (100 + 68.27) / 2, axis=0) - long_means
        low_unc = long_means - np.percentile(long_samples, (100 - 68.27) / 2, axis=0)

        return long_means, (high_unc + low_unc) / 2
    
    def get_theta_start_mcmc(self, method):
        threads = []
        result = MinResult()
        print(f"Starting {NUM_THREADS} threads")
        for i in range(NUM_THREADS):
            seed = random.randint(0, 0xffff_ffff_ffff_ffff)
            t = Thread(target=self.min_func_mcmc, args=(seed, method, result))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        result, f_value = result.get_value()
        print(f"Starting from point {result} with likelihood -{f_value} after {NUM_SUCCESSES} successful minima")
        #print(Hessian(lambda theta: -log_probability(theta))(result))
        return result

    def min_func_mcmc(self, seed, method, result):
        local_rng = random.Random()
        local_rng.seed(seed)
        while not result.is_satisfied():
            val = method.pick_parameters(local_rng)
            try:
                min_result = minimize(self.minimize_func, x0=val, method="Nelder-Mead", args=(result, method), options = {"maxiter": 500 * len(val)})
            except CompletedException:
                return
            if min_result.fun < MIN_LOG_LIKE:
                print(f"Thread successfully completed with log like {min_result.fun}, parameters {min_result.x}")
                result.set(min_result.x, min_result.fun)
            else:
                print(f"Attempt failed with log like {min_result.fun}")
                result.increment()

    def minimize_func(self, theta, result, method):
        if result.is_satisfied() or result.query_exceeded_attempts(MINIMIZATION_ATTEMPTS):
            raise CompletedException
        lp = -log_probability(theta, method, self.data_storage)
        #print(lp, theta)
        #print(-log_probability(theta / 100, method, self.data_storage))
        return lp

    def mcmc_fit(self, theta_start, output_name, method, generate=True):
        if generate:
            backend = emcee.backends.HDFBackend(output_name+".h5")
            backend.reset(N_WALKERS, self.n_free)
            old_tau = np.inf


            with Pool() as pool:
                sampler = emcee.EnsembleSampler(N_WALKERS, self.n_free, log_probability, args=(method, self.data_storage), backend=backend, pool=pool)
            
                pos = method.scatter_walkers(theta_start, N_WALKERS, data_storage=self.data_storage)
                
                for p in pos:
                    print(log_probability(p, method, self.data_storage))

                for sample in sampler.sample(pos, iterations=MAX_N_STEPS, progress=True):
                    if sampler.iteration % 500 == 0:
                        if np.max(sample.log_prob) < MINIMUM_LIKELIHOOD:
                            # MCMC will not converge.
                            print("Log probs were", sample.log_prob)
                            return None
                        if sampler.iteration >= 5_000:
                            # Check convergence

                            tau = sampler.get_autocorr_time(tol=0)

                            converged = np.all(tau * 100 < sampler.iteration)
                            converged &= np.all(np.abs(old_tau - tau) / tau < 0.01)
                            if converged:
                                print("Converged")
                                break
                            old_tau = tau
                    if sampler.iteration % 5000 == 500:
                        tau = sampler.get_autocorr_time(tol=0)
                        print(np.mean(sample.log_prob), tau)

        else:
            backend = emcee.backends.HDFBackend(output_name+".h5", read_only=True)
            sampler = emcee.EnsembleSampler(N_WALKERS, self.n_free, log_probability, args=(method, self.data_storage), backend=backend)

        return sampler


    def display(self, densities, true_densities, uncertainty_ratios,
        error, duration=5):

        FIG_DIRECTORY = "../../figs/"

        if not os.path.isdir(f"{FIG_DIRECTORY}{self.name}"):
            os.mkdir(f"{FIG_DIRECTORY}{self.name}")

        warnings.filterwarnings("ignore")

        densities /= np.nanmean(densities)

        PERCENTILE = 99.5# 95

        if true_densities is not None:
            true_densities /= np.nanmean(true_densities)
            ratios = (densities - true_densities) / (densities * uncertainty_ratios)
            make_slices(ratios, self.asteroid.grid_line, "$\\Delta\\rho / \\sigma_\\rho$", 'coolwarm', f"{FIG_DIRECTORY}{self.name}/fe-r", error, percentile=PERCENTILE, balance=True)
            make_gif(ratios, self.asteroid.grid_line, "$\\Delta\\rho / \\sigma_\\rho$", 'coolwarm', f"{FIG_DIRECTORY}{self.name}/fe-r.gif", duration=duration, percentile=PERCENTILE, balance=True)
            difference = (true_densities - densities) / densities

        print("Plotting density")
        make_slices(densities, self.asteroid.grid_line, "$\\rho$", 'plasma', f"{FIG_DIRECTORY}{self.name}/fe-d", error)
        make_gif(densities, self.asteroid.grid_line, "$\\rho$", 'plasma', f"{FIG_DIRECTORY}{self.name}/fe-d.gif", duration)
        
        print("Plotting uncertainty")
        make_slices(uncertainty_ratios, self.asteroid.grid_line, "$\\sigma_\\rho / \\rho$", 'Greys_r', f"{FIG_DIRECTORY}{self.name}/fe-u", error, PERCENTILE)
        make_gif(uncertainty_ratios, self.asteroid.grid_line, "$\\sigma_\\rho / \\rho$", 'Greys_r', f"{FIG_DIRECTORY}{self.name}/fe-u.gif", duration, PERCENTILE)

        if true_densities is not None:
            print("Plotting differences")
            make_slices(difference, self.asteroid.grid_line, "$\\Delta\\rho / \\rho$", 'PuOr_r', f"{FIG_DIRECTORY}{self.name}/fe-s", error, PERCENTILE, balance=True)
            make_gif(difference, self.asteroid.grid_line, "$\\Delta\\rho / \\rho$", 'PuOr_r', f"{FIG_DIRECTORY}{self.name}/fe-s.gif", duration, PERCENTILE, balance=True)

        warnings.filterwarnings("default")

    
if __name__ == "__main__":
    import fe, lumpy
    sys.path.append("..")
    from core import Indicator, TrueShape
    
    ELLIPSOID_AM = 1000
    k22a, k20a = -0.05200629, -0.2021978
    DIVISION = 99
    MAX_RADIUS = 2000# For the shape
    DOF = 9

    a = np.sqrt(5/3) * ELLIPSOID_AM * np.sqrt(1 - 2 * k20a + 12 * k22a)
    b = np.sqrt(5/3) * ELLIPSOID_AM * np.sqrt(1 - 2 * k20a - 12 * k22a)
    c = np.sqrt(5/3) * ELLIPSOID_AM * np.sqrt(1 + 4 * k20a)
    core_displacement = 300
    core_rad = 500
    core_vol = np.pi * 4 / 3 * core_rad**3
    ellipsoid_vol = np.pi * 4 / 3 * a * b * c
    density_factor_low = 0.5
    density_factor_high = 2
    core_shift_low = core_displacement * (core_vol * density_factor_low) / ellipsoid_vol
    core_shift_high = core_displacement * (core_vol * density_factor_high) / ellipsoid_vol

    asteroid = MCMCAsteroid("asym-ell", "../samples/den-core-move-3-0-samples.npy", 
        Indicator.ell_y_shift(ELLIPSOID_AM, k22a, k20a, -core_shift_high), TrueShape.core_shift(3, 500, core_displacement),
        1002.0081758422925, DIVISION, MAX_RADIUS, DOF, 933.1648422811957)

    # asteroid = MCMCAsteroid(f"den-core-sph", "../samples/den-core-sph-0-samples.npy", Indicator.ell(surface_am, k22, k20), surface_am, DIVISION, MAX_RADIUS, True, used_bulk_am=978.4541044108308)

    print(asteroid.pipeline(fe.FiniteElement, True, generate=False))