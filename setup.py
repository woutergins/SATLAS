from setuptools import setup
setup(
  name='satlas',
  packages=['satlas'],
  version='0.1.0b8',
  description='This Python package has been created with the goal of creating an easier interface for the analysis of data gathered from laser spectroscopy experiments. Support for fitting the spectra, using both chi2-fitting and Maximum Likelihood Estimation routines, are present.',
  author='Wouter Gins',
  author_email='woutergins@gmail.com',
  url='https://woutergins.github.io/satlas/',
  license='MIT',
  download_url='https://github.com/woutergins/satlas/tarball/0.1.0b7',
  keywords=['physics', 'hyperfine structure', 'fitting'],
  install_requires=['numpy',
                    'scipy',
                    'sympy',
                    'matplotlib',
                    'pandas',
                    'emcee',
                    'lmfit',
                    'progressbar2',
                    'h5py'],
  classifiers=['Development Status :: 4 - Beta',
               'Intended Audience :: Science/Research',
               'License :: OSI Approved :: MIT License',
               'Operating System :: Microsoft :: Windows',
               'Programming Language :: Python :: 2',
               'Programming Language :: Python :: 3',
               'Topic :: Scientific/Engineering :: Physics'],
)