"""
.. module:: SingleSpectrum
    :platform: Windows
    :synopsis: Implementation of class for the analysis of hyperfine
     structure spectra, including various fitting routines.

.. moduleauthor:: Wouter Gins <wouter.gins@fys.kuleuven.be>
.. moduleauthor:: Ruben de Groote <ruben.degroote@fys.kuleuven.be>
"""
import lmfit as lm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import satlas.profiles as p
from fractions import Fraction

from .isomerspectrum import IsomerSpectrum
from .spectrum import Spectrum
from .wigner import wigner_6j, wigner_3j
W6J = wigner_6j
W3J = wigner_3j

__all__ = ['SingleSpectrum']


class SingleSpectrum(Spectrum):

    r"""Class for the construction of a HFS spectrum, consisting of different
    peaks described by a certain profile. The number of peaks and their
    positions is governed by the atomic HFS.
    Calling an instance of the Spectrum class returns the response value of the
    HFS spectrum for that frequency in MHz.

    Parameters
    ----------
    I: float
        The nuclear spin.
    J: list of 2 floats
        The spins of the fine structure levels.
    ABC: list of 6 floats
        The hyperfine structure constants A, B and C for ground- and excited
        fine level. The list should be given as [A :sub:`lower`,
        A :sub:`upper`, B :sub:`lower`, B :sub:`upper`, C :sub:`upper`,
        C :sub:`lower`].
    centroid: float
        Centroid of the spectrum.
    fwhm: float or list of 2 floats, optional
        Depending on the used shape, the FWHM is defined by one or two floats.
        Defaults to [50.0, 50.0]
    scale: float, optional
        Sets the strength of the spectrum, defaults to 1.0. Comparable to the
        amplitude of the spectrum.

    Other parameters
    ----------------
    shape : string, optional
        Sets the transition shape. String is converted to lowercase. For
        possible values, see :attr:`Spectrum.__shapes__.keys()`.
        Defaults to Voigt if an incorrect value is supplied.
    racah_int: Boolean, optional
        If True, fixes the relative peak intensities to the Racah intensities.
        Otherwise, gives them equal intensities and allows them to vary during
        fitting.
    shared_fwhm: Boolean, optional
        If True, the same FWHM is used for all peaks. Otherwise, give them all
        the same initial FWHM and let them vary during the fitting.

    Attributes
    ----------
    fwhm : (list of) float or list of 2 floats
        Sets the FWHM for all the transtions. If :attr:`shared_fwhm` is True,
        this attribute is a list of FWHM values for each peak.
    relAmp : list of floats
        Sets the relative intensities of the transitions.
    scale : float
        Sets the amplitude of the global spectrum.
    background : float
        Sets the background of the global spectrum.
    ABC : list of 6 floats
        List of the hyperfine structure constants, organised as
        [A :sub:`lower`, A :sub:`upper`, B :sub:`lower`, B :sub:`upper`,
        C :sub:`upper`, C :sub:`lower`].
    n : integer
        Sets the number of Poisson sidepeaks.
    offset : float
        Sets the offset for the Poisson sidepeaks.
        The sidepeaks are located at :math:`i\cdot \text{offset}`,
        with :math:`i` the number of the sidepeak.
        Note: this means that a negative value indicates a sidepeak
        to the left of the main peak.
    poisson : float
        Sets the Poisson-factor for the Poisson sidepeaks.
        The amplitude of each sidepeak is multiplied by
        :math:`\text{poisson}^i/i!`, with :math:`i` the number of the sidepeak.

    Note
    ----
    The listed attributes are commonly accessed attributes for the end user.
    More are used, and should be looked up in the source code."""

    __shapes__ = {'gaussian': p.Gaussian,
                  'lorentzian': p.Lorentzian,
                  'voigt': p.Voigt}

    def __init__(self, I, J, ABC, centroid, fwhm=[50.0, 50.0], scale=1.0,
                 background=0.1, shape='voigt', racah_int=True,
                 shared_fwhm=True, n=0, poisson=0.68, offset=0):
        super(SingleSpectrum, self).__init__()
        shape = shape.lower()
        if shape not in self.__shapes__:
            print("""Given profile shape not yet supported.
            Defaulting to Voigt lineshape.""")
            shape = 'voigt'
            fwhm = [50.0, 50.0]

        self.I_value = {0.0: ((False, 0), (False, 0), (False, 0),
                              (False, 0), (False, 0), (False, 0)),
                        0.5: ((True, 1), (True, 1),
                              (False, 0), (False, 0), (False, 0), (False, 0)),
                        1.0: ((True, 1), (True, 1),
                              (True, 1), (True, 1),
                              (False, 0), (False, 0))
                        }
        self.J_lower_value = {0.0: ((False, 0), (False, 0), (False, 0)),
                              0.5: ((True, 1),
                                    (False, 0), (False, 0)),
                              1.0: ((True, 1),
                                    (True, 1), (False, 0))
                              }
        self.J_upper_value = {0.0: ((False, 0), (False, 0), (False, 0)),
                              0.5: ((True, 1),
                                    (False, 0), (False, 0)),
                              1.0: ((True, 1),
                                    (True, 1), (False, 0))
                              }
        self.shape = shape
        self.racah_int = racah_int
        self.shared_fwhm = shared_fwhm
        self.I = I
        self.J = J
        self.calculate_F_levels()
        self.calculate_energy_coefficients()
        self.calculate_transitions()

        self._vary = {}
        self.ratio = [None, None, None]

        self.ratioA = (None, 'lower')
        self.ratioB = (None, 'lower')
        self.ratioC = (None, 'lower')

        self.populate_params(ABC, fwhm, scale, background, n,
                             poisson, offset, centroid)

    def populate_params(self, ABC, fwhm, scale, background,
                        n, poisson, offset, centroid):
        par = lm.Parameters()
        if not self.shape.lower() == 'voigt':
            if self.shared_fwhm:
                par.add('FWHM', value=fwhm, vary=True, min=0)
            else:
                for label, val in zip(self.ftof, fwhm):
                    par.add('FWHM' + label, value=val, vary=True, min=0)
        else:
            if self.shared_fwhm:
                par.add('FWHMG', value=fwhm[0], vary=True, min=0)
                par.add('FWHML', value=fwhm[1], vary=True, min=0)
                val = 0.5346 * fwhm[1] + np.sqrt(0.2166 *
                                                 fwhm[1] ** 2
                                                 + fwhm[0] ** 2)
                par.add('TotalFWHM', value=val, vary=False,
                        expr='0.5346*FWHML+sqrt(0.2166*FWHML**2+FWHMG**2)')
            else:
                for label, val in zip(self.ftof, fwhm):
                    par.add('FWHMG' + label, value=val[0], vary=True, min=0)
                    par.add('FWHML' + label, value=val[1], vary=True, min=0)
                    val = 0.5346 * val[1] + np.sqrt(0.2166 * val[1] ** 2
                                                    + val[0] ** 2)
                    par.add('TotalFWHM' + str(i), value=val, vary=False,
                            expr='0.5346*FWHML' + str(i) +
                                 '+sqrt(0.2166*FWHML' + str(i) +
                                 '**2+FWHMG' + str(i) + '**2)')

        par.add('scale', value=scale, vary=self.racah_int, min=0)
        for label, amp in zip(self.ftof, self.initial_amplitudes):
            label = 'Amp' + label
            par.add(label, value=amp, vary=not self.racah_int, min=0)

        par.add('Al', value=ABC[0], vary=True)
        par.add('Au', value=ABC[1], vary=True)
        par.add('Bl', value=ABC[2], vary=True)
        par.add('Bu', value=ABC[3], vary=True)
        par.add('Cl', value=ABC[4], vary=True)
        par.add('Cu', value=ABC[5], vary=True)

        ratios = (self.ratioA, self.ratioB, self.ratioC)
        labels = (('Al', 'Au'), ('Bl', 'Bu'), ('Cl', 'Cu'))
        for r, (l, u) in zip(ratios, labels):
            if r[0] is not None:
                if r[1].lower() == 'lower':
                    fixed, free = l, u
                else:
                    fixed, free = u, l
                par[fixed].expr = str(r[0]) + '*' + free
                par[fixed].vary = False

        par.add('Centroid', value=centroid, vary=True)

        par.add('Background', value=background, vary=True, min=0)
        par.add('N', value=n, vary=False)
        if n > 0:
            par.add('Poisson', value=poisson, vary=False, min=0)
            par.add('Offset', value=offset, vary=False, min=None, max=-0.01)

        self.params = self.check_variation(par)

    def set_ratios(self, par):
        ratios = (self.ratioA, self.ratioB, self.ratioC)
        labels = (('Al', 'Au'), ('Bl', 'Bu'), ('Cl', 'Cu'))
        for r, (l, u) in zip(ratios, labels):
            if r[0] is not None:
                if r[1].lower() == 'lower':
                    fixed, free = l, u
                else:
                    fixed, free = u, l
                par[fixed].expr = str(r[0]) + '*' + free
                par[fixed].vary = False
        return par

    def check_variation(self, par):
        for key in self._vary.keys():
            if key in par.keys():
                par[key].vary = self._vary[key]
        par['N'].vary = False

        if self.I in self.I_value:
            Al, Au, Bl, Bu, Cl, Cu = self.I_value[self.I]
            if not Al[0]:
                par['Al'].vary, par['Al'].value = Al
            if not Au[0]:
                par['Au'].vary, par['Au'].value = Au
            if not Bl[0]:
                par['Bl'].vary, par['Bl'].value = Bl
            if not Bu[0]:
                par['Bu'].vary, par['Bu'].value = Bu
            if not Cl[0]:
                par['Cl'].vary, par['Cl'].value = Cl
            if not Cu[0]:
                par['Cu'].vary, par['Cu'].value = Cu
        if self.J[0] in self.J_lower_value:
            Al, Bl, Cl = self.J_lower_value[self.J[0]]
            if not Al[0]:
                par['Al'].vary, par['Al'].value = Al
            if not Bl[0]:
                par['Bl'].vary, par['Bl'].value = Bl
            if not Cl[0]:
                par['Cl'].vary, par['Cl'].value = Cl
        if self.J[self.num_lower] in self.J_upper_value:
            Au, Bu, Cu = self.J_upper_value[self.J[self.num_lower]]
            if not Au[0]:
                par['Au'].vary, par['Au'].value = Au
            if not Bu[0]:
                par['Bu'].vary, par['Bu'].value = Bu
            if not Cu[0]:
                par['Cu'].vary, par['Cu'].value = Cu
        return par

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, params):
        self._params = params
        self.calculate_energies()
        self.calculate_transition_locations()
        if not self.racah_int:
            self.set_amplitudes()
        self.set_fwhm()

    def set_amplitudes(self):
        for p, label in zip(self.parts, self.ftof):
            p.amp = self.params['Amp' + label].value

    def set_fwhm(self):
        if self.shape.lower() == 'voigt':
            fwhm = [[self.params['FWHMG'].value, self.params['FWHML'].value] for _ in self.ftof] if self.shared_fwhm else [[self.params['FWHMG' + label].value, self.params['FWHML' + label].value] for label in self.ftof]
        else:
            fwhm = [self.params['FWHM'].value for _ in self.ftof] if self.shared_fwhm else [self.params['FWHM' + label].value for label in self.ftof]
        for p, f in zip(self.parts, fwhm):
            p.fwhm = f

    def calculate_F_levels(self):
        F1 = np.arange(abs(self.I - self.J[0]), self.I+self.J[0]+1, 1)
        self.num_lower = len(F1)
        F2 = np.arange(abs(self.I - self.J[1]), self.I+self.J[1]+1, 1)
        self.num_upper = len(F2)
        F = np.append(F1, F2)
        self.J = np.append(np.ones(len(F1)) * self.J[0],
                           np.ones(len(F2)) * self.J[1])
        self.F = F

    def calculate_transitions(self):
        f_f = []
        indices = []
        amps = []
        for i, F1 in enumerate(self.F[:self.num_lower]):
            for j, F2 in enumerate(self.F[self.num_lower:]):
                if abs(F2 - F1) <= 1 and not F2 == F1 == 0.0:
                    j += self.num_lower
                    intensity = self.calculate_racah_intensity(self.J[i],
                                                               self.J[j],
                                                               self.F[i],
                                                               self.F[j])
                    if intensity > 0:
                        amps.append(intensity)
                        indices.append([i, j])
                        s = ''
                        temp = Fraction(F1).limit_denominator()
                        if temp.denominator == 1:
                            s += str(temp.numerator)
                        else:
                            s += str(temp.numerator) + '_' + str(temp.denominator)
                        s += '__'
                        temp = Fraction(F2).limit_denominator()
                        if temp.denominator == 1:
                            s += str(temp.numerator)
                        else:
                            s += str(temp.numerator) + '_' + str(temp.denominator)
                        f_f.append(s)
        self.ftof = f_f
        self.transition_indices = indices
        self.initial_amplitudes = amps
        self.parts = tuple(self.__shapes__[self.shape]() for _ in amps)

    def calculate_energy_coefficients(self):
        I, J, F = self.I, self.J, self.F
        C = (F*(F+1) - I*(I+1) - J*(J + 1)) * (J/J) if I > 0 else 0 * J
        D = (3*C*(C+1) - 4*I*(I+1)*J*(J+1)) / (2*I*(2*I-1)*J*(2*J-1))
        E = (10*(0.5*C)**3 + 20*(0.5*C)**2 + C*(-3*I*(I+1)*J*(J+1) + I*(I+1) + J*(J+1) + 3) - 5*I*(I+1)*J*(J+1)) / (I*(I-1)*(2*I-1)*J*(J-1)*(2*J-1))
        C = np.where(np.isfinite(C), 0.5 * C, 0)
        D = np.where(np.isfinite(D), 0.25 * D, 0)
        E = np.where(np.isfinite(E), E, 0)
        self.C, self.D, self.E = C, D, E

    def calculate_energies(self):
        r"""The hyperfine addition to a central frequency (attribute :attr:`centroid`)
        for a specific level is calculated. The formula comes from
        :cite:`Schwartz1955` and in a simplified form, reads

        .. math::
            C_F &= F(F+1) - I(I+1) - J(J+1)

            D_F &= \frac{3 C_F (C_F + 1) - 4 I (I + 1) J (J + 1)}{2 I (2 I - 1)
            J (2 J - 1)}

            E_F &= \frac{10 (\frac{C_F}{2})^3 + 20(\frac{C_F}{2})^2 + C_F(-3I(I
            + 1)J(J + 1) + I(I + 1) + J(J + 1) + 3) - 5I(I + 1)J(J + 1)}{I(I -
            1)(2I - 1)J(J - 1)(2J - 1)}

            E &= centroid + \frac{A C_F}{2} + \frac{B D_F}{4} + C E_F

        A, B and C are the dipole, quadrupole and octupole hyperfine
        parameters. Octupole contributions are calculated when both the
        nuclear and electronic spin is greater than 1, quadrupole contributions
        when they are greater than 1/2, and dipole contributions when they are
        greater than 0.

        Parameters
        ----------
        level: int, 0 or 1
            Integer referring to the lower (0) level, or the upper (1) level.
        F: integer or half-integer
            F-quantum number for which the hyperfine-corrected energy has to be
            calculated.

        Returns
        -------
        energy: float
            Energy in MHz."""
        A = np.append(np.ones(self.num_lower) * self.params['Al'].value,
                      np.ones(self.num_upper) * self.params['Au'].value)
        B = np.append(np.ones(self.num_lower) * self.params['Bl'].value,
                      np.ones(self.num_upper) * self.params['Bu'].value)
        C = np.append(np.ones(self.num_lower) * self.params['Cl'].value,
                      np.ones(self.num_upper) * self.params['Cu'].value)
        centr = np.append(np.zeros(self.num_lower),
                          np.ones(self.num_upper) * self.params['Centroid'].value)
        self.energies = centr + self.C * A + self.D * B + self.E * C

    def calculate_transition_locations(self):
        self.locations = [self.energies[ind_high] - self.energies[ind_low]
                          for (ind_low, ind_high) in self.transition_indices]

    @property
    def locations(self):
        return self._locations

    @locations.setter
    def locations(self, locations):
        self._locations = locations
        for p, l in zip(self.parts, locations):
            p.mu = l

    def set_variation(self, varyDict):
        """Sets the variation of the fitparameters as supplied in the
        dictionary.

        Parameters
        ----------
        varydict: dictionary
            A dictionary containing 'key: True/False' mappings

        Note
        ----
        The list of usable keys:

        * :attr:`FWHM` (only for profiles with one float for the FWHM)
        * :attr:`eta`  (only for the Pseudovoigt profile)
        * :attr:`FWHMG` (only for profiles with two floats for the FWHM)
        * :attr:`FWHML` (only for profiles with two floats for the FWHM)
        * :attr:`Al`
        * :attr:`Au`
        * :attr:`Bl`
        * :attr:`Bu`
        * :attr:`Cl`
        * :attr:`Cu`
        * :attr:`Centroid`
        * :attr:`Background`
        * :attr:`Poisson` (only if the attribute *n* is greater than 0)
        * :attr:`Offset` (only if the attribute *n* is greater than 0)"""
        for k in varyDict.keys():
            self._vary[k] = varyDict[k]

    def fix_ratio(self, value, target='upper', parameter='A'):
        """Fixes the ratio for a given hyperfine parameter to the given value.

        Parameters
        ----------
        value: float
            Value to which the ratio is set
        target: {'upper', 'lower'}
            Sets the target level. If 'upper', the upper parameter is
            calculated as lower * ratio, 'lower' calculates the lower
            parameter as upper * ratio.
        parameter: {'A', 'B', 'C'}
            Selects which hyperfine parameter to set the ratio for."""
        if target.lower() not in ['lower', 'upper']:
            raise KeyError("Target must be 'lower' or 'upper'.")
        if parameter.lower() not in ['a', 'b', 'c']:
            raise KeyError("Parameter must be 'A', 'B' or 'C'.")
        if parameter.lower() == 'a':
            self.ratioA = (value, target)
        if parameter.lower() == 'b':
            self.ratioB = (value, target)
        if parameter.lower() == 'c':
            self.ratioC = (value, target)
        self.params = self.set_ratios(self.params)

    def calculate_racah_intensity(self, J1, J2, F1, F2, order=1.0):
        return float((2 * F1 + 1) * (2 * F2 + 1) * \
                     W6J(J2, F2, self.I, F1, J1, order) ** 2)

    def sanitize_input(self, x, y, yerr=None):
        return x, y, yerr

    def bootstrap(self, x, y, bootstraps=100, samples=None, selected=True):
        """Given an experimental spectrum of counts, generate a number of
        bootstrapped resampled spectra, fit these, and return a pandas
        DataFrame containing result of fitting these resampled spectra.

        Parameters
        ----------
        x: array_like
            Frequency in MHz.
        y: array_like
            Counts corresponding to :attr:`x`.

        Other Parameters
        ----------------
        bootstraps: integer, optional
            Number of bootstrap samples to generate, defaults to 100.
        samples: integer, optional
            Number of counts in each bootstrapped spectrum, defaults to
            the number of counts in the supplied spectrum.
        selected: boolean, optional
            Selects if only the parameters in :attr:`self.selected` are saved
            in the DataFrame. Defaults to True (saving only the selected).

        Returns
        -------
        DataFrame
            DataFrame containing the results of fitting the bootstrapped
            samples."""
        total = np.cumsum(y)
        dist = total / float(y.sum())
        names, var, varerr = self.vars(selection='chisquare')
        selected = self.selected if selected else names
        v = [name for name in names if name in selected]
        data = pd.DataFrame(index=np.arange(0, bootstraps + 1),
                            columns=v)
        stderrs = pd.DataFrame(index=np.arange(0, bootstraps + 1),
                               columns=v)
        v = [var[i] for i, name in enumerate(names) if name in selected]
        data.loc[0] = v
        v = [varerr[i] for i, name in enumerate(names) if name in selected]
        stderrs.loc[0] = v
        if samples is None:
            samples = y.sum()
        length = len(x)

        for i in range(bootstraps):
            newy = np.bincount(
                    np.searchsorted(
                            dist,
                            np.random.rand(samples)
                            ),
                    minlength=length
                    )
            self.chisquare_spectroscopic_fit(x, newy)
            names, var, varerr = self.vars(selection='chisquare')
            v = [var[i] for i, name in enumerate(names) if name in selected]
            data.loc[i + 1] = v
            v = [varerr[i] for i, name in enumerate(names) if name in selected]
            stderrs.loc[i + 1] = v
        pan = {'data': data, 'stderr': stderrs}
        pan = pd.Panel(pan)
        return pan

    def __add__(self, other):
        """Add two spectra together to get an :class:`IsomerSpectrum`.

        Parameters
        ----------
        other: Spectrum
            Other spectrum to add.

        Returns
        -------
        IsomerSpectrum
            An Isomerspectrum combining both spectra."""
        if isinstance(other, SingleSpectrum):
            l = [self, other]
        elif isinstance(other, IsomerSpectrum):
            l = [self] + other.spectra
        return IsomerSpectrum(l)

    def __radd__(self, other):
        if other == 0:
            return self
        else:
            return self.__add__(other)

    def seperate_response(self, x):
        """Get the response for each seperate spectrum for the values :attr:`x`
        , without background.

        Parameters
        ----------
        x : float or array_like
            Frequency in MHz.

        Returns
        -------
        list of floats or NumPy arrays
            Seperate responses of spectra to the input :attr:`x`."""
        return [self(x)]

    def __call__(self, x):
        """Get the response for frequency :attr:`x` (in MHz) of the spectrum.

        Parameters
        ----------
        x : float or array_like
            Frequency in MHz

        Returns
        -------
        float or NumPy array
            Response of the spectrum for each value of :attr:`x`."""
        if self.params['N'].value > 0:
            s = np.zeros(x.shape)
            for i in range(self.params['N'].value + 1):
                s += (self.params['Poisson'].value ** i) * sum([prof(x + i * self.params['Offset'].value)
                                                for prof in self.parts]) \
                    / np.math.factorial(i)
            s = s * self.params['scale'].value
        else:
            s = self.params['scale'].value * sum([prof(x) for prof in self.parts])
        return s + self.params['Background'].value

    ###############################
    #      PLOTTING ROUTINES      #
    ###############################

    def plot(self, x=None, y=None, yerr=None,
             no_of_points=10**4, ax=None, show=True, label=True,
             legend=None, data_legend=None):
        """Routine that plots the hfs, possibly on top of experimental data.
        Parameters
        ----------
        x: array
            Experimental x-data. If None, a suitable region around
            the peaks is chosen to plot the hfs.
        y: array
            Experimental y-data.
        yerr: array
            Experimental errors on y.
        no_of_points: int
            Number of points to use for the plot of the hfs.
        ax: matplotlib axes object
            If provided, plots on this axis
        show: Boolean
            If True, the plot will be shown at the end.
        label: Boolean
            If True, the plot will be labeled.
        legend: String, optional
            If given, an entry in the legend will be made for the spectrum.
        data_legend: String, optional
            If given, an entry in the legend will be made for the experimental
            data.
        Returns
        -------
        None"""

        if ax is None:
            fig, ax = plt.subplots(1, 1)
            toReturn = fig, ax
        else:
            toReturn = None

        if x is None:
            ranges = []
            fwhm = self.parts[0].fwhm

            for pos in self.locations:
                r = np.linspace(pos - 4 * fwhm,
                                pos + 4 * fwhm,
                                2 * 10**2)
                ranges.append(r)
            superx = np.sort(np.concatenate(ranges))

        else:
            superx = np.linspace(x.min(), x.max(), no_of_points)

        if x is not None and y is not None:
            ax.errorbar(x, y, yerr, fmt='o', label=data_legend)
        ax.plot(superx, self(superx), label=legend)
        if label:
            ax.set_xlabel('Frequency (MHz)')
            ax.set_ylabel('Counts')
        if show:
            plt.show()
        return toReturn

    def plot_spectroscopic(self, **kwargs):
        """Routine that plots the hfs, possibly on top of
        experimental data. It assumes that the y data is drawn from
        a Poisson distribution (e.g. counting data).
        Parameters
        ----------
        x: array
            Experimental x-data. If None, a suitable region around
            the peaks is chosen to plot the hfs.
        y: array
            Experimental y-data.
        no_of_points: int
            Number of points to use for the plot of the hfs.
        ax: matplotlib axes object
            If provided, plots on this axis
        show: Boolean
            if True, the plot will be shown at the end.
        Returns
        -------
        None
        """
        y = kwargs.get('y', None)
        if y is not None:
            yerr = np.sqrt(y)
            yerr[np.isclose(yerr, 0)] = 1.0
        else:
            yerr = None
        kwargs['yerr'] = yerr
        self.plot(**kwargs)