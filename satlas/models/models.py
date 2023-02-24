"""
Implementation of a class for the analysis of linear data.

.. moduleauthor:: Wouter Gins <wouter.gins@kuleuven.be>
"""

import lmfit as lm
from satlas.models.basemodel import BaseModel, SATLASParameters
import numpy as np

__all__ = ['PolynomialModel', 'MiscModel']


class PolynomialModel(BaseModel):

    r"""Constructs a polynomial response."""

    def __init__(self, args):
        """:class:`.PolynomialModel` creates a general polynomial
        of the order given by *len(args)-1*. The given coefficients
        are ordered lowest to highest order.

        Parameters
        ----------
        args: iterable of values
            Iterable containing all the values for the
            coefficients. Polynomial order is determined
            by the length. args[0] is the coefficient
            of order 0, etc..."""
        super(PolynomialModel, self).__init__()
        self._populate_params(args)

    @property
    def params(self):
        return self._parameters

    @params.setter
    def params(self, params):
        p = params.copy()
        p._prefix = self._prefix
        self._parameters = self._check_variation(p)

    ####################################
    #      INITIALIZATION METHODS      #
    ####################################

    def _populate_params(self, args):
        # Prepares the params attribute with the initial values
        par = SATLASParameters()
        for i, val in reversed(list(enumerate(args))):
            par.add('Order' + str(i) + 'Coeff', value=val, vary=True)
        self.params = self._check_variation(par)

        self.names = [p for p in self.params.keys()]

    ###########################
    #      MAGIC METHODS      #
    ###########################

    def __call__(self, x):
        return np.polyval([self.params[p].value for p in self.names], x)

class MiscModel(BaseModel):

    r"""Constructs a response from a supplied function.
    Call signature is

    def func(x, par):

        a = par[0]

        b = par[1]

        ...

        return y"""

    def __init__(self, func, args, name_list=None):
        """The :class:`.MiscModel` takes a supplied function *func* and list of starting
        argument parameters *args* to contruct an object that responds with the
        given function for the parameter values. A list of names can also
        be supplied to customize the parameter names.

        Parameters
        ----------
        func: callable
            A callable function with call signature *func(x, args)*.
        args: list of values
            List of starting values for the parameters. The number of parameters is based
            on the length of the list of arguments.
        name_list: list of strings, optional
            List of names to be supplied to the parameters. The order of the names
            and the order of the parameters is the same, so *name_list[0]* corresponds
            to *args[0]*."""
        super(MiscModel, self).__init__()
        self.func = func
        self.name_list = name_list
        self._populate_params(*args)

    @property
    def params(self):
        return self._parameters

    @params.setter
    def params(self, params):
        p = params.copy()
        p._prefix = self._prefix
        self._parameters = self._check_variation(p)

    ####################################
    #      INITIALIZATION METHODS      #
    ####################################

    def _populate_params(self, *args):
        # Prepares the params attribute with the initial values
        par = SATLASParameters()
        names = []
        if self.name_list is None:
            for i, val in enumerate(args):
                par.add('Param' + str(i + 1), value=val, vary=True)
                names.append('Param' + str(i + 1))
        else:
            for name, val in zip(self.name_list, args):
                par.add(name, value=val, vary=True)
                names.append(name)

        self.params = self._check_variation(par)
        self.names = names

    ###########################
    #      MAGIC METHODS      #
    ###########################

    def __call__(self, x):
        return self.func(x, [self.params[p].value for p in self.names])
