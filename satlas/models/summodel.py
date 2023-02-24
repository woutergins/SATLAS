"""
Implementation of a class for the analysis of hyperfine structure spectra with isomeric presence.

.. moduleauthor:: Wouter Gins <wouter.gins@kuleuven.be>
.. moduleauthor:: Ruben de Groote <ruben.degroote@kuleuven.be>
"""
import copy
from satlas.models.basemodel import BaseModel
from satlas.utilities import poisson_interval
import matplotlib.pyplot as plt
import numpy as np


__all__ = ['SumModel']


class SumModel(BaseModel):

    """Create a model that sums all the underlying models for a single input variable."""

    def __init__(self, models):
        """Initializes the HFS by providing a list of :class:`.HFSModel`
        objects.

        Parameters
        ----------
        models: list of :class:`.HFSModel` instances
            A list containing the models."""
        super(SumModel, self).__init__()
        self.models = models
        for i, model in enumerate(self.models):
            model._add_prefix('s' + str(i) + '_')
        self._set_params()
        self.shared = []

    def _set_params(self):
        for model in self.models:
            try:
                p.add_many(*model.params.values())
            except:
                p = model.params.copy()
        self.params = p

    def _add_prefix(self, value):
        for model in self.models:
            model._add_prefix(value)
        self._set_params()

    def get_chisquare_mapping(self):
        return np.hstack([f.get_chisquare_mapping() for f in self.models])

    def get_lnprior_mapping(self, params):
        return sum([f.get_lnprior_mapping(params) for f in self.models])

    @property
    def shared(self):
        """Contains all parameters which share the same value among all models."""
        return self._shared

    @shared.setter
    def shared(self, value):
        params = self.params.copy()
        self._shared = value
        for name in self._shared:
            selected_list = [p for p in params.keys() if name in p]
            try:
                selected_name = selected_list[0]
                for p in selected_list[1:]:
                    params[p].expr = selected_name
            except IndexError:
                pass
        self.params = params

    @property
    def params(self):
        """Instance of lmfit.Parameters object characterizing the
        shape of the HFS."""
        return self._parameters

    @params.setter
    def params(self, params):
        self._parameters = params.copy()
        for spec in self.models:
            spec.params = self._parameters.copy()

    def seperate_response(self, x, background=False):
        """Get the response for each seperate spectrum for the values *x*,
        without background.

        Parameters
        ----------
        x : float or array_like
            Frequency in MHz.

        Other parameters
        ----------------
        background: boolean
            If True, each spectrum has the same background. If False,
            the background of each spectrum is assumed to be 0.

        Returns
        -------
        list of floats or NumPy arrays
            Seperate responses of models to the input *x*."""
        background_vals = [np.polyval([s.params[par_name].value for par_name in s.params if par_name.startswith('Background')], x) for s in self.models]
        return [s(x) - b * (1-background) for s, b in zip(self.models, background_vals)]

    ###############################
    #      PLOTTING ROUTINES      #
    ###############################

    def plot(self, x=None, y=None, yerr=None, ax=None, plot_kws={}, plot_seperate=True, show=True, legend=None, data_legend=None, xlabel='Frequency (MHz)', ylabel='Counts'):
        """Routine that plots the hfs of all the models,
        possibly on top of experimental data.

        Parameters
        ----------
        x: list of arrays
            Experimental x-data. If list of Nones, a suitable region around
            the peaks is chosen to plot the hfs.
        y: list of arrays
            Experimental y-data.
        yerr: list of arrays
            Experimental errors on y.
        plot_seperate: boolean, optional
            Controls if the underlying models are drawn as well, or only
            the sum. Defaults to False.
        no_of_points: int
            Number of points to use for the plot of the hfs if
            experimental data is given.
        ax: matplotlib axes object
            If provided, plots on this axis.
        show: boolean
            If True, the plot will be shown at the end.
        legend: string, optional
            If given, an entry in the legend will be made for the spectrum.
        data_legend: string, optional
            If given, an entry in the legend will be made for the experimental
            data.
        xlabel: string, optional
            If given, sets the xlabel to this string. Defaults to 'Frequency (MHz)'.
        ylabel: string, optional
            If given, sets the ylabel to this string. Defaults to 'Counts'.
        indicate: boolean, optional
            If set to True, dashed lines are drawn to indicate the location of the
            transitions, and the labels are attached. Defaults to False.
        model: boolean, optional
            If given, the region around the fitted line will be shaded, with
            the luminosity indicating the pmf of the Poisson
            distribution characterized by the value of the fit. Note that
            the argument *yerr* is ignored if *model* is True.
        normalized: Boolean
            If True, the data and fit are plotted normalized such that the highest
            data point is one.
        distance: float, optional
            Controls how many FWHM deviations are used to generate the plot.
            Defaults to 4.

        Returns
        -------
        fig, ax: matplotlib figure and axes"""
        if ax is None:
            fig, ax = plt.subplots(1, 1)
        else:
            fig = ax.get_figure()
        toReturn = fig, ax

        if x is not None and y is not None:
            try:
                ax.errorbar(x, y, yerr=[y - yerr['low'], yerr['high'] - y], fmt='o', label=data_legend)
            except:
                ax.errorbar(x, y, yerr=yerr, fmt='o', label=data_legend)

        plot_kws['background'] = False
        plot_copy = copy.deepcopy(plot_kws)
        plot_copy['model'] = False
        x_points = np.array([])
        line_counter = 1
        for m in self.models:
            plot_copy['legend'] = 'I=' + str(m.I)
            try:
                color = ax.lines[-1].get_color()
            except IndexError:
                color = next(ax._get_lines.prop_cycler)['color']
            m.plot(x=x, y=y, yerr=yerr, show=False, ax=ax, plot_kws=plot_copy)
            # plot_kws['indicate'] = False
            x_points = np.append(x_points, ax.lines[-1].get_xdata())
            if not plot_seperate:
                ax.lines.pop(-1)
            if x is not None:
                ax.lines.pop(-1 - plot_seperate)
            while not next(ax._get_lines.prop_cycler)['color'] == color:
                pass
            if plot_seperate:
                c = next(ax._get_lines.prop_cycler)['color']
                for l in ax.lines[line_counter:]:
                    l.set_color(c)
                while not next(ax._get_lines.prop_cycler)['color'] == c:
                    pass
            line_counter = len(ax.lines)
        x = np.sort(x_points)
        model = plot_kws.pop('model', False)
        if model:
            colormap = plot_kws.pop('colormap', 'bone_r',)
            min_loc = [s.locations.min() for s in self.models]
            max_loc = [s.locations.max() for s in self.models]
            range = (min(min_loc), max(max_loc))
            from scipy import optimize
            max_counts = np.ceil(-optimize.brute(lambda x: -self(x), (range,), full_output=True, Ns=1000, finish=optimize.fmin)[1])
            min_counts = [self.params[par_name].value for par_name in self.params if par_name.endswith('Background0')][0]
            min_counts = np.floor(max(0, min_counts - 3 * min_counts ** 0.5))
            y = np.arange(min_counts, max_counts + 3 * max_counts ** 0.5 + 1)
            X, Y = np.meshgrid(x, y)
            from scipy import stats
            z = stats.poisson(self(X)).pmf(Y)

            z = z / z.sum(axis=0)
            ax.imshow(z, extent=(x.min(), x.max(), y.min(), y.max()), cmap=plt.get_cmap(colormap))
            line, = ax.plot(x, self(x), label=legend, lw=0.5)
        else:
            ax.plot(x, self(x))
        ax.legend(loc=0)

        # ax.set_xlabel(xlabel)
        # ax.set_ylabel(ylabel)

        if show:
            plt.show()
        return toReturn

    def plot_spectroscopic(self, x=None, y=None, plot_kws={}, **kwargs):
        """Routine that plots the hfs of all the models, possibly on
        top of experimental data. It assumes that the y data is drawn from
        a Poisson distribution (e.g. counting data).

        Parameters
        ----------
        x: list of arrays
            Experimental x-data. If list of Nones, a suitable region around
            the peaks is chosen to plot the hfs.
        y: list of arrays
            Experimental y-data.
        yerr: list of arrays
            Experimental errors on y.
        no_of_points: int
            Number of points to use for the plot of the hfs.
        ax: matplotlib axes object
            If provided, plots on this axis
        show: Boolean
            if True, the plot will be shown at the end.

        Returns
        -------
        fig, ax: matplotlib figure and axes"""

        if y is not None:
            ylow, yhigh = poisson_interval(y)
            yerr = {'low': ylow, 'high': yhigh}
        else:
            yerr = None
        return self.plot(x=x, y=y, yerr=yerr, plot_kws=plot_kws, **kwargs)

    def __add__(self, other):
        """Adding an SumModel results in a new SumModel
        with the new spectrum added.

        Returns
        -------
        SumModel"""
        if isinstance(other, SumModel):
            models = self.models + other.models
            return SumModel(models)
        else:
            try:
                return other.__add__(self)
            except:
                raise TypeError('unsupported operand type(s)')

    def __call__(self, x):
        """Get the response for frequency *x* (in MHz) of the spectrum.

        Parameters
        ----------
        x : float or array_like
            Frequency in MHz

        Returns
        -------
        float or NumPy array
            Response of the spectrum for each value of *x*."""
        return np.sum([s(x) for s in self.models], axis=0)
