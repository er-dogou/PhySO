import torch
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.lines import Line2D
import matplotlib.gridspec as gridspec
from sklearn.neighbors import KernelDensity
from IPython.display import display, clear_output

class RunLogger:
    """
    Custom logger function.
    """

    def __init__ (self, save_path = None, do_save = False):
        self.save_path = save_path
        self.do_save   = do_save
        self.initialize()

    def initialize (self):
        # Epoch specific
        self.epoch = None

        self.overall_max_R_history        = []
        self.hall_of_fame                 = []

        self.epochs_history               = []
        self.loss_history                 = []

        self.mean_R_train_history         = []
        self.mean_R_history               = []
        self.max_R_history                = []

        self.R_history                    = []
        self.R_history_train              = []

        self.best_prog_complexity_history = []
        self.mean_complexity_history      = []

        self.n_physical                   = []
        self.lengths_of_physical          = []
        self.lengths_of_unphysical        = []

    def log(self, epoch, batch, model, rewards, keep, notkept, loss_val):

        # Epoch specific
        self.epoch   = epoch
        self.R       = rewards
        self.batch   = batch
        self.keep    = keep
        self.notkept = notkept
        best_prog_idx_epoch  = rewards.argmax()
        self.best_prog_epoch = batch.programs.get_prog(best_prog_idx_epoch)
        self.programs_epoch  = batch.programs.get_programs_array()


        if epoch == 0:
            self.overall_max_R_history       = [rewards.max()]
            self.hall_of_fame                = [batch.programs.get_prog(best_prog_idx_epoch)]
        if epoch> 0:
            if rewards.max() > np.max(self.overall_max_R_history):
                self.overall_max_R_history.append(rewards.max())
                self.hall_of_fame.append(batch.programs.get_prog(best_prog_idx_epoch))
            else:
                self.overall_max_R_history.append(self.overall_max_R_history[-1])

        self.epochs_history         .append( epoch                             )
        self.loss_history           .append( loss_val.cpu().detach().numpy()   )

        self.mean_R_train_history   .append( rewards[keep].mean()              )
        self.mean_R_history         .append( rewards.mean()                    )
        self.max_R_history          .append( rewards.max()                     )


        self.R_history              .append( rewards                           )
        self.R_history_train        .append( rewards[keep]                     )

        self.best_prog_complexity_history .append(batch.programs.tokens.complexity[best_prog_idx_epoch].sum())
        self.mean_complexity_history      .append(batch.programs.tokens.complexity.sum(axis=1).mean())

        self.R_history_array        = np.array(self.R_history)
        self.R_history_train_array  = np.array(self.R_history_train)

        self.n_physical              .append( batch.programs.is_physical.sum() )
        self.lengths_of_physical     .append( self.batch.programs.n_lengths[ self.batch.programs.is_physical] )
        self.lengths_of_unphysical   .append( self.batch.programs.n_lengths[~self.batch.programs.is_physical] )

        self.pareto_logger()

        # Saving log
        if self.do_save:
            self.save_log()

    def save_log (self):
        # Initial df
        if self.epoch == 0:
            df0 = pd.DataFrame(columns=['epoch', 'reward', 'complexity', 'length', 'is_physical', 'is_elite', 'program'])
            df0.to_csv(self.save_path, index=False)

        # Current batch log
        is_elite = np.full(self.batch.batch_size, False)
        is_elite[self.keep] = True
        programs_str = np.array([prog.get_infix_str() for prog in self.batch.programs.get_programs_array()])

        df = pd.DataFrame()
        df["epoch"]       = np.full(self.batch.batch_size, self.epoch)
        df["reward"]      = self.R
        df["complexity"]  = self.batch.programs.n_complexity
        df["length"]      = self.batch.programs.n_lengths
        df["is_physical"] = self.batch.programs.is_physical
        df["is_elite"]    = is_elite
        df["program"]     = programs_str

        # Saving current df
        df.to_csv(self.save_path, mode='a', index=False, header=False)

        return None


    def pareto_logger(self,):
        curr_complexities = self.batch.programs.n_complexity
        curr_rewards      = self.R
        curr_batch        = self.batch

        # Init
        if self.epoch == 0:
            self.pareto_complexities  = np.arange(0,10*curr_batch.max_time_step)
            self.pareto_rewards       = np.full(shape=(self.pareto_complexities.shape), fill_value = np.NaN)
            self.pareto_programs      = np.full(shape=(self.pareto_complexities.shape), fill_value = None, dtype=object)

        # Update with current epoch info
        for i,c in enumerate(self.pareto_complexities):
            # Idx in batch of programs having complexity c
            arg_have_c = np.argwhere(curr_complexities.round() == c)
            if len(arg_have_c) > 0:
                # Idx in batch of the program having complexity c and having max reward
                arg_have_c_and_max = arg_have_c[curr_rewards[arg_have_c].argmax()]
                # Max reward of this program
                max_r_at_c = curr_rewards[arg_have_c_and_max]
                # If reward > currently max reward for this complexity or empty, replace
                if self.pareto_rewards[i] <= max_r_at_c or np.isnan(self.pareto_rewards[i]):
                    self.pareto_programs [i] = curr_batch.programs.get_prog(arg_have_c_and_max[0])
                    self.pareto_rewards  [i] = max_r_at_c

    def get_pareto_front(self,):
        # Postprocessing
        # Keeping only valid pareto candidates
        mask_pareto_valid = (~np.isnan(self.pareto_rewards)) & (self.pareto_rewards>0)
        pareto_rewards_valid      = self.pareto_rewards      [mask_pareto_valid]
        pareto_programs_valid     = self.pareto_programs     [mask_pareto_valid]
        pareto_complexities_valid = self.pareto_complexities [mask_pareto_valid]
        # Computing front
        pareto_front_r            = [pareto_rewards_valid       [0]]
        pareto_front_programs     = [pareto_programs_valid      [0]]
        pareto_front_complexities = [pareto_complexities_valid  [0]]
        for i,r in enumerate(pareto_rewards_valid):
            # Only keeping candidates with higher reward than candidates having a smaller complexity
            if r > pareto_front_r[-1]:
                pareto_front_r            .append(r)
                pareto_front_programs     .append(pareto_programs_valid     [i])
                pareto_front_complexities .append(pareto_complexities_valid [i])

        pareto_front_complexities = np.array(pareto_front_complexities)
        pareto_front_programs     = np.array(pareto_front_programs)
        pareto_front_r            = np.array(pareto_front_r)
        pareto_front_rmse         = ((1/pareto_front_r)-1)*self.batch.dataset.y_target.std().cpu().detach().numpy()

        return pareto_front_complexities, pareto_front_programs, pareto_front_r, pareto_front_rmse

    @property
    def best_prog(self):
        return self.hall_of_fame[-1]


class RunVisualiser:
    """
    Custom run visualiser.
    """

    def __init__ (self, epoch_refresh_rate = 10, save_path = None, do_show=True, do_save=False):
        self.epoch_refresh_rate = epoch_refresh_rate
        self.figsize   = (40,18)
        self.save_path = save_path
        self.save_path_log = ''.join(save_path.split('.')[:-1]) + "_log.csv" # save_path with extension replaced by _log.csv
        self.do_show   = do_show
        self.do_save   = do_save

    def initialize (self):
        self.fig = plt.figure(figsize=self.figsize)
        gs  = gridspec.GridSpec(3, 3)
        self.ax0 = self.fig.add_subplot(gs[0, 0])
        self.ax1 = self.fig.add_subplot(gs[0, 1])
        div = make_axes_locatable(self.ax1)
        self.cax = div.append_axes("right", size="4%", pad=0.4)
        self.ax2 = self.fig.add_subplot(gs[1, 0])
        self.ax3 = self.fig.add_subplot(gs[1, 1])
        self.ax4 = self.fig.add_subplot(gs[:2, 2])
        # 3rd line
        self.ax5 = self.fig.add_subplot(gs[2, 0])
        self.ax6 = self.fig.add_subplot(gs[2, 1])
        div = make_axes_locatable(self.ax6)
        self.cax6 = div.append_axes("right", size="4%", pad=0.4)
        self.ax7 = self.fig.add_subplot(gs[2, 2])
        div = make_axes_locatable(self.ax7)
        self.cax7 = div.append_axes("right", size="4%", pad=0.4)

    def update_plot (self,):
        epoch      = self.run_logger.epoch
        run_logger = self.run_logger
        batch      = self.batch

        # -------- Reward vs epoch --------
        curr_ax = self.ax0
        curr_ax.clear()
        curr_ax.plot(run_logger.epochs_history, run_logger.mean_R_history        , 'b'            , linestyle='solid' , alpha = 0.6, label="Mean")
        curr_ax.plot(run_logger.epochs_history, run_logger.mean_R_train_history  , 'r'            , linestyle='solid' , alpha = 0.6, label="Mean train")
        curr_ax.plot(run_logger.epochs_history, run_logger.overall_max_R_history , 'k'            , linestyle='solid' , alpha = 1.0, label="Overall Best")
        curr_ax.plot(run_logger.epochs_history, run_logger.max_R_history         , color='orange' , linestyle='solid' , alpha = 0.6, label="Best of epoch")
        curr_ax.set_ylabel("Reward")
        curr_ax.set_xlabel("Epochs")
        curr_ax.legend()

        # -------- Reward distrbution vs epoch --------
        curr_ax = self.ax1
        cmap = plt.get_cmap("viridis")
        fading_plot_nepochs       = epoch
        fading_plot_ncurves       = 20
        fading_plot_max_alpha     = 1.
        fading_plot_bins          = 100
        fading_plot_kde_bandwidth = 0.05
        curr_ax.clear()
        self.cax.clear()
        # Plotting last "fading_plot_nepochs" epoch on "fading_plot_ncurves" curves
        plot_epochs = []
        for i in range (fading_plot_ncurves+1):
            frac = i/fading_plot_ncurves
            plot_epoch = int(epoch - frac*fading_plot_nepochs)
            plot_epochs.append(plot_epoch)
            prog = 1 - frac
            alpha = fading_plot_max_alpha*(prog)
            # Histogram
            bins_dens = np.linspace(0., 1, fading_plot_bins)
            kde = KernelDensity(kernel="gaussian", bandwidth=fading_plot_kde_bandwidth
                               ).fit(run_logger.R_history_train_array[plot_epoch][:, np.newaxis])
            dens = 10**kde.score_samples(bins_dens[:, np.newaxis])
            # Plot
            curr_ax.plot(bins_dens, dens, alpha=alpha, linewidth=0.5, c=cmap(prog))
        # Colorbar
        normcmap = plt.matplotlib.colors.Normalize(vmin=plot_epochs[0], vmax=plot_epochs[-1])
        cbar = self.fig.colorbar(plt.cm.ScalarMappable(norm=normcmap, cmap=cmap), cax=self.cax, pad=0.005)
        cbar.set_label('epochs', rotation=90,labelpad=30)
        curr_ax.set_xlim([0, 1.])
        curr_ax.set_ylabel("Density")
        curr_ax.set_xlabel("Reward")

        # -------- Complexity --------
        curr_ax = self.ax2
        curr_ax.clear()
        curr_ax.plot(run_logger.epochs_history, run_logger.best_prog_complexity_history, 'orange', linestyle='solid'   ,  label="Best of epoch")
        curr_ax.plot(run_logger.epochs_history, run_logger.mean_complexity_history     , 'b',      linestyle='solid'   ,  label="Mean")
        curr_ax.set_ylabel("Complexity")
        curr_ax.set_xlabel("Epochs")
        curr_ax.legend()

        # -------- Loss --------
        curr_ax = self.ax3
        curr_ax.clear()
        curr_ax.plot(run_logger.epochs_history, run_logger.loss_history, 'grey', label="loss")
        curr_ax.set_ylabel("Loss")
        curr_ax.set_xlabel("Epochs")
        curr_ax.legend()

        # -------- Fit --------
        curr_ax = self.ax4
        curr_ax.clear()
        # Cut on dim
        cut_on_dim = 0
        x = batch.dataset.X[cut_on_dim]
        # Plot data
        x_expand = 0.5
        n_plot = 100
        stack = []
        for x_dim in batch.dataset.X:
            x_dim_min = x.min().cpu().detach().numpy()
            x_dim_max = x.max().cpu().detach().numpy()
            x_dim_plot = torch.tensor(np.linspace(x_dim_min-x_expand, x_dim_max+x_expand, n_plot))
            stack.append(x_dim_plot)
        X_plot = torch.stack(stack).to(batch.dataset.detected_device)
        x_plot = X_plot[cut_on_dim]

        # Data points
        curr_ax.plot(x.cpu().detach().numpy(), batch.dataset.y_target.cpu().detach().numpy(), 'ko', markersize=10)
        x_plot_cpu = x_plot.detach().cpu().numpy()

        # Best overall program
        y_plot = run_logger.best_prog(X_plot).detach().cpu().numpy()
        if y_plot.shape == (): y_plot = np.full(n_plot, y_plot)
        curr_ax.plot(x_plot_cpu, y_plot, color='k', linestyle='solid', linewidth=2)

        # Best program of epoch
        y_plot = run_logger.best_prog_epoch(X_plot).detach().cpu().numpy()
        if y_plot.shape == (): y_plot = np.full(n_plot, y_plot)
        curr_ax.plot(x_plot_cpu, y_plot, color='orange', linestyle='solid', linewidth=2)

        # Train programs
        for prog in run_logger.programs_epoch[run_logger.keep]:
            y_plot =  prog(X_plot).detach().cpu().numpy()
            if y_plot.shape == (): y_plot = np.full(n_plot, y_plot)
            curr_ax.plot(x_plot_cpu, y_plot, color='r', alpha=0.05, linestyle='solid')

        # Other programs
        for prog in run_logger.programs_epoch[run_logger.notkept]:
            y_plot =  prog(X_plot).detach().cpu().numpy()
            if y_plot.shape == (): y_plot = np.full(n_plot, y_plot)
            curr_ax.plot(x_plot_cpu, y_plot, color='b', alpha=0.05, linestyle='solid')

        # Plot limits
        y_min = batch.dataset.y_target.min().cpu().detach().numpy()
        y_max = batch.dataset.y_target.max().cpu().detach().numpy()
        curr_ax.set_ylim(y_min-0.1*np.abs(y_min), y_max+0.1*np.abs(y_max))
        custom_lines = [
            Line2D([0], [0], color='k',      lw=3),
            Line2D([0], [0], color='orange', lw=3),
            Line2D([0], [0], color='r',      lw=3),
            Line2D([0], [0], color='b',      lw=3),]
        curr_ax.legend(custom_lines, ['Overall Best', 'Best of epoch', 'Train', 'Others'])

        # -------- Number of physical progs --------
        curr_ax = self.ax5
        curr_ax.plot(run_logger.epochs_history, run_logger.n_physical, 'grey', label="Physical count")
        curr_ax.set_xlabel("Epochs")
        curr_ax.set_ylabel("Physical count")


        # -------- Lengths of physical distribution vs epoch --------
        curr_ax  = self.ax6
        curr_cax = self.cax6

        cmap = plt.get_cmap("viridis")
        fading_plot_nepochs       = epoch
        fading_plot_ncurves       = 20
        fading_plot_max_alpha     = 1.
        fading_plot_bins          = 100
        fading_plot_kde_bandwidth = 1.
        curr_ax.clear()
        curr_cax.clear()
        # Plotting last "fading_plot_nepochs" epoch on "fading_plot_ncurves" curves
        plot_epochs = []
        for i in range (fading_plot_ncurves+1):
            frac = i/fading_plot_ncurves
            plot_epoch = int(epoch - frac*fading_plot_nepochs)
            plot_epochs.append(plot_epoch)
            prog = 1 - frac
            alpha = fading_plot_max_alpha*(prog)
            # Distribution data
            distrib_data = self.run_logger.lengths_of_physical[plot_epoch]
            # If non empty selection, compute pdf and plot it
            if distrib_data.shape[0] > 0:
                # Histogram
                bins_dens = np.linspace(0., self.run_logger.batch.max_time_step, fading_plot_bins)
                kde = KernelDensity(kernel="gaussian", bandwidth=fading_plot_kde_bandwidth
                                   ).fit(distrib_data[:, np.newaxis])
                dens = 10**kde.score_samples(bins_dens[:, np.newaxis])
                # Plot
                curr_ax.plot(bins_dens, dens, alpha=alpha, linewidth=0.5, c=cmap(prog))
        # Colorbar
        normcmap = plt.matplotlib.colors.Normalize(vmin=plot_epochs[0], vmax=plot_epochs[-1])
        cbar = self.fig.colorbar(plt.cm.ScalarMappable(norm=normcmap, cmap=cmap), cax=curr_cax, pad=0.005)
        cbar.set_label('epochs', rotation=90,labelpad=30)
        curr_ax.set_xlim([0, self.run_logger.batch.max_time_step])
        curr_ax.set_ylabel("Density")
        curr_ax.set_xlabel("Lengths (physical)")

        # -------- Lengths of unphysical distribution vs epoch --------
        curr_ax  = self.ax7
        curr_cax = self.cax7
        curr_fig = self.fig

        cmap = plt.get_cmap("viridis")
        fading_plot_nepochs       = epoch
        fading_plot_ncurves       = 20
        fading_plot_max_alpha     = 1.
        fading_plot_bins          = 100
        fading_plot_kde_bandwidth = 1.
        curr_ax.clear()
        curr_cax.clear()
        # Plotting last "fading_plot_nepochs" epoch on "fading_plot_ncurves" curves
        plot_epochs = []
        for i in range (fading_plot_ncurves+1):
            frac = i/fading_plot_ncurves
            plot_epoch = int(epoch - frac*fading_plot_nepochs)
            plot_epochs.append(plot_epoch)
            prog = 1 - frac
            alpha = fading_plot_max_alpha*(prog)
            # Distribution data
            distrib_data = self.run_logger.lengths_of_unphysical[plot_epoch]
            # If non empty selection, compute pdf and plot it
            if distrib_data.shape[0] > 0:
                # Histogram
                bins_dens = np.linspace(0., self.run_logger.batch.max_time_step, fading_plot_bins)
                kde = KernelDensity(kernel="gaussian", bandwidth=fading_plot_kde_bandwidth
                                   ).fit(distrib_data[:, np.newaxis])
                dens = 10**kde.score_samples(bins_dens[:, np.newaxis])
                # Plot
                curr_ax.plot(bins_dens, dens, alpha=alpha, linewidth=0.5, c=cmap(prog))
        # Colorbar
        normcmap = plt.matplotlib.colors.Normalize(vmin=plot_epochs[0], vmax=plot_epochs[-1])
        cbar = curr_fig.colorbar(plt.cm.ScalarMappable(norm=normcmap, cmap=cmap), cax=curr_cax, pad=0.005)
        cbar.set_label('epochs', rotation=90,labelpad=30)
        curr_ax.set_xlim([0, self.batch.max_time_step])
        curr_ax.set_ylabel("Density")
        curr_ax.set_xlabel("Lengths (unphysical)")

    def make_prints(self):
        print("--- Epoch %s ---\n"%(str(self.run_logger.epoch).zfill(5)))

        # Overall best
        print("\nOverall best  at R=%f"%(self.run_logger.overall_max_R_history[-1]))
        print("  -> Raw expression        : \n%s"%(self.run_logger.best_prog.get_infix_pretty(do_simplify=False, )))
        #print("  -> Simplified expression : \n%s"%(run_logger.best_prog.get_infix_pretty(do_simplify=True , )))

        # Best of epoch
        print("\nBest of epoch at R=%f"%(self.run_logger.R.max()))
        print("  -> Raw expression        : \n%s"%(self.run_logger.best_prog_epoch.get_infix_pretty(do_simplify=False, )))
        #print("  -> Simplified expression : \n%s"%(run_logger.best_prog_epoch.get_infix_pretty(do_simplify=True , )))

        #print("************************************************* Best programs *************************************************")
        ## Batch status
        #print("\nBest programs")
        #for i in range(n_keep):
        #    print("  -> R = %f: \n%s"%(run_logger.R[keep][i], programs[keep][i].get_infix_pretty(do_simplify=False)))
        #    print("------------------------------------------------------------")
        #print("*****************************************************************************************************************")

    def make_visualisation (self):
        # -------- Prints --------
        self.make_prints()
        # -------- Plot update --------
        self.update_plot()
        # -------- Display --------
        display(self.fig)
        clear_output(wait=True)

    def save_visualisation (self):
        # -------- Prints --------
        print("  -> epoch %s"%(str(self.run_logger.epoch).zfill(5)))
        # -------- Plot update --------
        self.update_plot()
        # -------- Save plot --------
        self.fig.savefig(self.save_path)
        # -------- Save curves data --------
        df = pd.DataFrame()


        return None

    def visualise (self, run_logger, batch):
        epoch = run_logger.epoch
        self.run_logger = run_logger
        self.batch      = batch
        if epoch == 0:
            self.initialize()
        if epoch%self.epoch_refresh_rate == 0:
            try:
                if self.do_show:
                    self.make_visualisation()
                if self.do_save:
                    self.save_visualisation()
            except:
                print("Unable to make visualisation plots.")
