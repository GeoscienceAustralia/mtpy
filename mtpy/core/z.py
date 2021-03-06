#!/usr/bin/env python

"""
=============
z module
=============

Classes
---------
    * Z --> deals with impedance tesnsor.
    * Tipper --> deals with Tipper matrix.

"""

# =================================================================
import cmath
import copy
import math

import numpy as np

import mtpy.utils.calculator as MTcc
import mtpy.utils.exceptions as MTex

from mtpy.utils.mtpylog import MtPyLog
import logging

# get a logger object for this module, using the utility class MtPyLog to
# config the logger
logger = MtPyLog().get_mtpy_logger(__name__)
#logger.setLevel(logging.INFO)  #this sets the module specific log Level
# =================================================================


# ------------------------
class Z(object):
    """
    Z class - generates an impedance tensor (Z) object.

    Z is a complex array of the form (n_freq, 2, 2),
    with indices in the following order:

        - Zxx: (0,0)
        - Zxy: (0,1)
        - Zyx: (1,0)
        - Zyy: (1,1)

    All errors are given as standard deviations (sqrt(VAR))

    Arguments
    ------------

        **z_array** : numpy.ndarray(n_freq, 2, 2)
                    array containing complex impedance values

        **z_err_array** : numpy.ndarray(n_freq, 2, 2)
                       array containing error values (standard deviation)
                       of impedance tensor elements
        **freq** : np.ndarray(n_freq)
                 array of frequency values corresponding to impedance tensor
                 elements.

    =============== ===========================================================
    Attributes      Description
    =============== ===========================================================
    freq             array of frequencies corresponding to elements of z
    rotation_angle   angle of which data is rotated by
    z                impedance tensor
    z_err             estimated errors of impedance tensor
    resistivity      apparent resisitivity estimated from z in Ohm-m
    resistivity_err  apparent resisitivity error
    phase            impedance phase (deg)
    phase_err        error in impedance phase
    =============== ===========================================================

    =================== =======================================================
    Methods             Description
    =================== =======================================================
    det                  calculates determinant of z with errors
    invariants           calculates the invariants of z
    inverse              calculates the inverse of z
    remove_distortion    removes distortion given a distortion matrix
    remove_ss            removes static shift by assumin Z = S * Z_0
    norm                 calculates the norm of Z
    only1d               zeros diagonal components and computes
                         the absolute valued mean of the off-diagonal
                         components.
    only2d               zeros diagonal components
    res_phase            computes resistivity and phase
    rotate               rotates z positive clockwise, angle assumes
                         North is 0.
    set_res_phase        recalculates z and z_err, needs attribute freq
    skew                 calculates the invariant skew (off diagonal trace)
    trace                calculates the trace of z
    =================== =======================================================

    Example
    -----------

        >>> import mtpy.core.z as mtz
        >>> import numpy as np
        >>> z_test = np.array([[0+0j, 1+1j], [-1-1j, 0+0j]])
        >>> z_object = mtz.Z(z_array=z_test, freq=[1])
        >>> z_object.rotate(45)
        >>> z_object.resistivity


    """

    def __init__(self, z_array=None, z_err_array=None, freq=None):
        """
        Initialise an instance of the Z class.

        Arguments

            **z_array** : numpy.ndarray(n_freq, 2, 2)
                        array containing complex impedance values

            **z_err_array** : numpy.ndarray(n_freq, 2, 2)
                           array containing error values (standard deviation)
                           of impedance tensor elements

            **freq** : np.ndarray(n_freq)
                     array of frequency values corresponding to impedance
                     tensor elements.

        Initialises the attributes with None
        """

        self._z = z_array
        self._z_err = z_err_array
        self._freq = freq

        if z_array is not None:
            if len(z_array.shape) == 2 and z_array.shape == (2, 2):
                if z_array.dtype in ['complex', 'float', 'int']:
                    self._z = np.zeros((1, 2, 2), 'complex')
                    self._z[0] = z_array

        if z_err_array is not None:
            if len(z_err_array.shape) == 2 and z_err_array.shape == (2, 2):
                if z_err_array.dtype in ['complex', 'float', 'int']:
                    self._z_err = np.zeros((1, 2, 2), 'complex')
                    self._z_err[0] = z_err_array

        self.rotation_angle = 0.
        if self._z is not None:
            self.rotation_angle = np.zeros((len(self._z)))

        # make attributes for resistivity and phase
        self._resistivity = None
        self._resistivity_err = None

        self._phase = None
        self._phase_err = None

        if self._z is not None:
            self._compute_res_phase()

    # ---frequency-------------------------------------------------------------
    def _set_freq(self, lo_freq):
        """
        Set the array of freq.

        Arguments
                -------------

            **lo_freq** : list or array of frequnecies (Hz)

        No test for consistency!
        """

        if not np.iterable(lo_freq):
            lo_freq = np.array([lo_freq])

        if self.z is not None:
            if len(self.z.shape) == 3:
                #if len(lo_freq) is not len(self.z):
                if len(lo_freq) != len(self.z):
                    logger.warn('length of freq list/array not correct'
                           '({0} instead of {1})'.format(len(lo_freq),
                                                         len(self.z)))
                    return

        self._freq = np.array(lo_freq)

        # for consistency recalculate resistivity and phase
        if self._z is not None:
            try:
                self._compute_res_phase()
            except IndexError:
                logging.error('Need to input frequency array')

    def _get_freq(self):
        if self._freq is None:
            return None
        else:
            return np.array(self._freq)

    freq = property(_get_freq, _set_freq, doc='array of frequencies in Hz')

    # ----impedance tensor ---------------------------------------------------
    def _set_z(self, z_array):
        """
        Set the attribute 'z'.

        Arguments
                -------------

            **z_array** : np.ndarray(nfreq, 2, 2)
                        complex impedance tensor array

        Test for shape, but no test for consistency!

        Nulling the rotation_angle

        """

        try:
            if len(z_array.shape) == 3 and z_array.shape[1:3] == (2, 2):
                if z_array.dtype in ['complex', 'float', 'int']:
                    self._z = z_array
        except IndexError:
            try:
                if len(z_array.shape) == 2 and z_array.shape == (2, 2):
                    if z_array.dtype in ['complex', 'float', 'int']:
                        self._z = np.zeros((1, 2, 2), 'complex')
                        self._z[0] = z_array
            except IndexError:
                logger.error('provided Z array does not have correct dimensions- Z unchanged')

        if isinstance(self.rotation_angle, float):
            self.rotation_angle = np.repeat(self.rotation_angle,
                                            len(self._z))

        # for consistency recalculate resistivity and phase
        if self._z is not None:
            try:
                self._compute_res_phase()
            except IndexError:
                logger.error('Need to input frequency array')

    def _get_z(self):
        return self._z

    z = property(_get_z, _set_z, doc="impedance tensor")

    # ----impedance error-----------------------------------------------------
    def _set_z_err(self, z_err_array):
        """
        Set the attribute z_err

        Arguments
                ------------

            **z_err_array** : np.ndarray(nfreq, 2, 2)
                           error of impedance tensor array as standard deviation

        Test for shape, but no test for consistency!

        """
        if z_err_array.shape != self.z.shape:
            logger.warn('z_err_array shape {0} is not same shape as z {1}'.format(
                z_err_array.shape, self.z.shape))
        self._z_err = z_err_array

        # for consistency recalculate resistivity and phase
        if self._z_err is not None and self._z is not None:
            try:
                self._compute_res_phase()
            except IndexError:
                logger.error('Need to input frequency array')

    def _get_z_err(self):
        return self._z_err

    z_err = property(_get_z_err, _set_z_err, doc='impedance tensor error')

    # ---real part of impedance tensor-----------------------------------------
    def _get_real(self):
        """
        Return the real part of Z.
        """

        if self.z is None:
            logger.warn('z array is None - cannot calculate real')
            return

        return np.real(self.z)

    def _set_real(self, real_array):
        """
        Set the real part of 'z'.

        Arguments
                -------------

            **real_array** : np.ndarray(nfreq, 2, 2)
                          real part of impedance tensor array

        Test for shape, but no test for consistency!

        """

        if (self.z is not None) and (self.z.shape != real_array.shape):
            logger.error('shape of "real" array does not match shape of' + \
                  'Z array: {0} ; {1}'.format(real_array.shape, self.z.shape))
            return

        # assert real array:
        if np.linalg.norm(np.imag(real_array)) != 0:
            logger.error('Error - array "real" is not real valued !')
            return

        ii_arr = np.complex(0, 1)

        if self.z is not None:
            z_new = real_array + ii_arr * self.imag()
        else:
            z_new = real_array

        self.z = z_new

        # for consistency recalculate resistivity and phase
        self._compute_res_phase()

    # real = property(_get_real, _set_real, doc='Real part of Z')
    # ---imaginary part of impedance tensor------------------------------------
    def _get_imag(self):
        """ Return the imaginary part of Z.
        """

        if self.z is None:
            logger.error('z array is None - cannot calculate imag')
            return

        return np.imag(self.z)

    def _set_imag(self, imag_array):
        """
        Set the imaginary part of 'z'.

        Arguments
                -------------

            **imag_array** : np.ndarray(nfreq, 2, 2)
                           imaginary part of impedance tensor array

        Test for shape, but no test for consistency!

        """

        if (self.z is not None) and (self.z.shape != imag_array.shape):
            logger.error('Error - shape of "imag" array does not match shape of' + \
                  'Z array: {0} ; {1}'.format(imag_array.shape, self.z.shape))
            return

        # assert real array:
        if np.linalg.norm(np.imag(imag_array)) != 0:
            logger.error('Error - array "imag" is not real valued !')
            return

        i_arr = np.complex(0, 1)

        if self.z is not None:
            z_new = self.real() + i_arr * imag_array
        else:
            z_new = i_arr * imag_array

        self.z = z_new

        # for consistency recalculate resistivity and phase
        self._compute_res_phase()

    # imag = property(_get_imag, _set_imag, doc='Imaginary part of Z ')

    # -----resistivity and phase----------------------------------------------
    def _compute_res_phase(self):
        """ Compute and sets attributes
                * resistivity
                * phase
                * resistivity_err
                * phase_err
        values for resistivity are in in Ohm-m and phase in degrees.
        """
        if self.freq is None:
            logger.info('self.freq is None - cannot calculate Res/Phase')
            # This is due to spectra type EDI file!!!
            return

        if self.z is None:
            logger.info('Z array is None - cannot calculate Res/Phase')
            return

        self._resistivity_err = None
        self._phase_err = None
        if self.z_err is not None:
            self._resistivity_err = np.zeros_like(self.z_err)
            self._phase_err = np.zeros_like(self.z_err)

        self._resistivity = np.zeros_like(self.z, dtype='float')
        self._phase = np.zeros_like(self.z, dtype='float')

        # calculate resistivity and phase
        for idx_f in range(len(self.z)):
            for ii in range(2):
                for jj in range(2):
                    self._resistivity[idx_f, ii, jj] = np.abs(self.z[idx_f, ii, jj]) ** 2 / \
                        self.freq[idx_f] * 0.2
                    self._phase[idx_f, ii, jj] = math.degrees(cmath.phase(
                        self.z[idx_f, ii, jj]))

                    if self.z_err is not None:
                        r_err, phi_err = MTcc.z_error2r_phi_error(
                            np.real(self.z[idx_f, ii, jj]),
                            self.z_err[idx_f, ii, jj],
                            np.imag(self.z[idx_f, ii, jj]),
                            self.z_err[idx_f, ii, jj])

                        self._resistivity_err[idx_f, ii, jj] = \
                            0.4 * np.abs(self.z[idx_f, ii, jj]) / \
                            self.freq[idx_f] * r_err
                        self._phase_err[idx_f, ii, jj] = phi_err

    def _get_resistivity(self):
        return self._resistivity

    def _get_resistivity_err(self):
        return self._resistivity_err

    def _get_phase(self):
        return self._phase

    def _get_phase_err(self):
        return self._phase_err

    def _set_resistivity(self, *kwargs):
        logger.info ("cannot be set individually - use method 'set_res_phase'!")

    def _set_resistivity_err(self, *kwargs):
        logger.info ("cannot be set individually - use method 'set_res_phase'!")

    def _set_phase(self, *kwargs):
        logger.info("cannot be set individually - use method 'set_res_phase'!")

    def _set_phase_err(self, *kwargs):
        logger.info("cannot be set individually - use method 'set_res_phase'!")

    resistivity = property(_get_resistivity,
                           _set_resistivity,
                           doc='Resistivity array')
    resistivity_err = property(_get_resistivity_err,
                               _set_resistivity_err,
                               doc='Resistivity error array')

    phase = property(_get_phase,
                     _set_phase,
                     doc='Phase array')
    phase_err = property(_get_phase_err,
                         _set_phase_err,
                         doc='Phase error array')

    def set_res_phase(self, res_array, phase_array, reserr_array=None,
                      phaseerr_array=None):
        """
        Set values for resistivity (res - in Ohm m) and phase
        (phase - in degrees), including error propagation.

        Updates the attributes
                        * z
                        * z_err

        """
        if self.z is not None:
            z_new = copy.copy(self.z)

            if self.z.shape != res_array.shape:
                logger.error('Error - shape of "res" array does not match shape' + \
                      'of Z array: {0} ; {1}'.format(res_array.shape, self.z.shape))
                return

            if self.z.shape != phase_array.shape:
                logger.error('Error - shape of "phase" array does not match shape' + \
                      'of Z array: {0} ; {1}'.format(phase_array.shape, self.z.shape))
                return
        else:
            z_new = np.zeros(res_array.shape, 'complex')

            if res_array.shape != phase_array.shape:
                logger.error('Error - shape of "phase" array does not match shape' + \
                      'of "res" array: {0} ; {1}'.format(phase_array.shape, res_array.shape))
                return

        if (self.freq is None) or (len(self.freq) != len(res_array)):
            raise MTex.MTpyError_EDI('ERROR - cannot set res without correct' +
                                     'freq information - proper "freq" ' +
                                     'attribute must be defined')

        # assert real array:
        if np.linalg.norm(np.imag(res_array)) != 0:
            raise MTex.MTpyError_inputarguments('Error - array "res" is not' +
                                                'real valued !')

        if np.linalg.norm(np.imag(phase_array)) != 0:
            raise MTex.MTpyError_inputarguments('Error - array "phase" is' +
                                                'not real valued !')

        for idx_f in range(len(z_new)):
            for ii in range(2):
                for jj in range(2):
                    abs_z = np.sqrt(5 * self.freq[idx_f] *
                                    res_array[idx_f, ii, jj])
                    z_new[idx_f, ii, jj] = cmath.rect(abs_z,
                                                      np.radians(phase_array[idx_f, ii, jj]))

        self.z = z_new

        # ---------------------------
        # error propagation:
        if reserr_array is None or phaseerr_array is None:
            return

        if self.z_err is not None:
            z_err_new = copy.copy(self.z_err)

            try:
                if self.z_err.shape != reserr_array.shape:
                    logger.error('Error - shape of "reserr" array does not match' + \
                          'shape of Zerr array: {0} ; {1}'.format(
                              reserr_array.shape, self.z_err.shape))
                    return

                if self.z_err.shape != phaseerr_array.shape:
                    logger.error('Error - shape of "phase" array does not match' + \
                          'shape of Zerr array: {0} ; {1}'.format(
                              phase_array.shape, self.z.shape))
                    return
            except AttributeError:
                logger.error('Error - "phaseerr" or "reserr" is/are not array(s) - Zerr not set')
                self.z_err = None
                return

        else:
            z_err_new = np.zeros(reserr_array.shape, 'float')
            try:
                if reserr_array.shape != phaseerr_array.shape:
                    logger.error('Error - shape of "phase" array does not match' + \
                          'shape of Zerr array: {0} ; {1}'.format(
                              reserr_array.shape,  self.z_err.shape))
                    return
            except AttributeError:
                logger.error('Error - "phaseerr" or "reserr" is/are not array(s) -' + \
                      ' Zerr not set')
                return

        for idx_f in range(len(z_err_new)):
            for ii in range(2):
                for jj in range(2):
                    abs_z = np.sqrt(5 * self.freq[idx_f] *
                                    res_array[idx_f, ii, jj])
                    rel_error_res = reserr_array[idx_f, ii, jj] / \
                        res_array[idx_f, ii, jj]
                    # relative error varies by a factor of 0.5, which is the
                    # exponent in the relation between them:
                    abs_z_error = 0.5 * abs_z * rel_error_res

                    z_err_new[idx_f, ii, jj] = max(MTcc.propagate_error_polar2rect(
                        abs_z,
                        abs_z_error,
                        phase_array[idx_f, ii, jj],
                        phaseerr_array[idx_f, ii, jj]))

        self.z_err = z_err_new

        # for consistency recalculate resistivity and phase
        self._compute_res_phase()

    def _get_inverse(self):
        """
            Return the inverse of Z.

            (no error propagtaion included yet)

        """

        if self.z is None:
            logger.war('z array is "None" - I cannot invert that')
            return

        inverse = copy.copy(self.z)
        for idx_f in range(len(inverse)):
            try:
                inverse[idx_f, :, :] = np.array(
                    (np.matrix(self.z[idx_f, :, :])).I)
            except:
                raise MTex.MTpyError_Z('The {0}ith impedance'.format(idx_f + 1) +
                                       'tensor cannot be inverted')

        return inverse

    inverse = property(_get_inverse, doc='Inverse of Z')

    def rotate(self, alpha):
        """
        Rotate Z array by angle alpha.

        Rotation angle must be given in degrees. All angles are referenced
        to geographic North, positive in clockwise direction.
        (Mathematically negative!)

        In non-rotated state, X refs to North and Y to East direction.

        Updates the attributes
            - *z*
            - *z_err*
            - *zrot*
            - *resistivity*
            - *phase*
            - *resistivity_err*
            - *phase_err*

        """

        if self.z is None:
            logger.warn('Z array is "None" - I cannot rotate that')
            return

        # check for iterable list/set of angles - if so, it must have length
        # 1 or same as len(tipper):
        if np.iterable(alpha) == 0:
            try:
                degreeangle = float(alpha % 360)
            except ValueError:
                logger.error('"Angle" must be a valid number (in degrees)')
                return

            # make an n long list of identical angles
            lo_angles = [degreeangle for ii in self.z]
        else:
            if len(alpha) == 1:
                try:
                    degreeangle = float(alpha % 360)
                except ValueError:
                    logger.error('"Angle" must be a valid number (in degrees)')
                    return
                # make an n long list of identical angles
                lo_angles = [degreeangle for ii in self.z]
            else:
                try:
                    lo_angles = [float(ii % 360) for ii in alpha]
                except ValueError:
                    logger.error('"Angles" must be valid numbers (in degrees)')
                    return

        self.rotation_angle = np.array([(oldangle + lo_angles[ii]) % 360
                                        for ii, oldangle in enumerate(self.rotation_angle)])

        if len(lo_angles) != len(self.z):
            logger.warn('Wrong number of "angles" - I need {0}'.format(len(self.z)))
            # self.rotation_angle = 0.
            return

        z_rot = copy.copy(self.z)
        z_err_rot = copy.copy(self.z_err)

        for idx_freq in range(len(self.z)):

            angle = lo_angles[idx_freq]
            if np.isnan(angle):
                angle = 0.

            if self.z_err is not None:
                z_rot[idx_freq], z_err_rot[idx_freq] = \
                    MTcc.rotatematrix_incl_errors(self.z[idx_freq, :, :],
                                                  angle,
                                                  self.z_err[idx_freq, :, :])
            else:
                z_rot[idx_freq], z_err_rot = \
                    MTcc.rotatematrix_incl_errors(self.z[idx_freq, :, :],
                                                  angle)

        self.z = z_rot
        if self.z_err is not None:
            self.z_err = z_err_rot

        # for consistency recalculate resistivity and phase
        self._compute_res_phase()

    def remove_ss(self, reduce_res_factor_x=1., reduce_res_factor_y=1.):
        """
        Remove the static shift by providing the respective correction factors
        for the resistivity in the x and y components.
        (Factors can be determined by using the "Analysis" module for the
        impedance tensor)

        Assume the original observed tensor Z is built by a static shift S
        and an unperturbated "correct" Z0 :

             * Z = S * Z0

        therefore the correct Z will be :
            * Z0 = S^(-1) * Z

        Arguments
        ------------

            **reduce_res_factor_x** : float or iterable list or array
                                    static shift factor to be applied to x
                                    components (ie z[:, 0, 1]).  This is
                                    assumed to be in resistivity scale

            **reduce_res_factor_y** : float or iterable list or array
                                    static shift factor to be applied to y
                                    components (ie z[:, 1, 0]).  This is
                                    assumed to be in resistivity scale

        Returns
                --------------

            **S** : np.ndarray ((2, 2))
                    static shift matrix,

            **Z0**: corrected Z   (over all freq)

        .. note:: The factors are in resistivity scale, so the
                  entries of  the matrix "S" need to be given by their
                  square-roots!

        """

        # check for iterable list/set of reduce_res_factor_x - if so, it must
        # have length 1 or same as len(z):
        if np.iterable(reduce_res_factor_x) == 0:
            try:
                x_factor = float(reduce_res_factor_x)
            except ValueError:
                logger.error('reduce_res_factor_x must be a valid numbers')
                return

            lo_x_factors = np.repeat(x_factor, len(self.z))
        else:
            if len(reduce_res_factor_x) == 1:
                try:
                    x_factor = float(reduce_res_factor_x)
                except ValueError:
                    logging.error('reduce_res_factor_x must be a valid numbers')
                    return
                lo_x_factors = np.repeat(x_factor, len(self.z))
            else:
                try:
                    lo_x_factors = np.repeat(x_factor,
                                             len(reduce_res_factor_x))
                except ValueError:
                    logging.error( '"reduce_res_factor_x" must be valid numbers')
                    return

        if len(lo_x_factors) != len(self.z):
            logging.error('Wrong number Number of reduce_res_factor_x - need {0}'.format(len(self.z)))
            return

        # check for iterable list/set of reduce_res_factor_y - if so,
        # it must have length 1 or same as len(z):
        if np.iterable(reduce_res_factor_y) == 0:
            try:
                y_factor = float(reduce_res_factor_y)
            except ValueError:
                logging.error('"reduce_res_factor_y" must be a valid numbers')
                return

            lo_y_factors = np.repeat(y_factor, len(self.z))
        else:
            if len(reduce_res_factor_y) == 1:
                try:
                    y_factor = float(reduce_res_factor_y)
                except ValueError:
                    logging.error( '"reduce_res_factor_y" must be a valid numbers')
                    return
                lo_y_factors = np.repeat(y_factor, len(self.z))
            else:
                try:
                    lo_y_factors = np.repeat(y_factor,
                                             len(reduce_res_factor_y))
                except ValueError:
                    logging.error('"reduce_res_factor_y" must be valid numbers')
                    return

        if len(lo_y_factors) != len(self.z):
            logging.error( 'Wrong number Number of "reduce_res_factor_y"' + \
                  '- need {0} '.format(len(self.z)))
            return

        z_corrected = copy.copy(self.z)
        static_shift = np.zeros((len(self.z), 2, 2))

        for idx_f in range(len(self.z)):
            # correct for x-direction
            z_corrected[idx_f, 0, :] = self.z[idx_f, 0, :] / \
                np.sqrt(lo_x_factors[idx_f])
            # correct for y-direction
            z_corrected[idx_f, 1, :] = self.z[idx_f, 1, :] / \
                np.sqrt(lo_y_factors[idx_f])
            # make static shift array
            static_shift[idx_f, 0, 0] = np.sqrt(lo_x_factors[idx_f])
            static_shift[idx_f, 1, 1] = np.sqrt(lo_y_factors[idx_f])

        return static_shift, z_corrected

    def remove_distortion(self, distortion_tensor, distortion_err_tensor=None):
        """
        Remove distortion D form an observed impedance tensor Z to obtain
        the uperturbed "correct" Z0:
        Z = D * Z0

        Propagation of errors/uncertainties included

                Arguments
                ------------
                        **distortion_tensor** : np.ndarray(2, 2, dtype=real)
                                              real distortion tensor as a 2x2

                        **distortion_err_tensor** : np.ndarray(2, 2, dtype=real),
                                                                          default is None

                Returns
                -----------
                        **distortion_tensor** :  np.ndarray(2, 2, dtype='real')
                                               input distortion tensor
                        **z_corrected** : np.ndarray(num_freq, 2, 2, dtype='complex')
                                        impedance tensor with distorion removed

                        **z_corrected_err** : np.ndarray(num_freq, 2, 2, dtype='complex')
                                                            impedance tensor error after distortion is removed

                Example
                ----------
                        >>> import mtpy.core.z as mtz
                        >>> distortion = np.array([[1.2, .5],[.35, 2.1]])
                        >>> d, new_z, new_z_err = z_obj.remove_distortion(distortion)
        """

        if distortion_err_tensor is None:
            distortion_err_tensor = np.zeros_like(distortion_tensor)
        # for all freq, calculate D.Inverse, then obtain Z0 = D.I * Z
        try:
            if not (len(distortion_tensor.shape) in [2, 3]) and \
                    (len(distortion_err_tensor.shape) in [2, 3]):
                raise ValueError('Shape not the same')
            if len(distortion_tensor.shape) == 3 or \
                    len(distortion_err_tensor.shape) == 3:
                logger.info('Distortion is not time-dependent - take only first' + \
                      'of given distortion tensors')
                try:
                    distortion_tensor = distortion_tensor[0]
                    distortion_err_tensor = distortion_err_tensor[0]
                except IndexError:
                    raise ValueError('distortion tensor the wrong shape')

            if not (distortion_tensor.shape == (2, 2)) and \
                    (distortion_err_tensor.shape == (2, 2)):
                raise ValueError('Shape not the same')

            distortion_tensor = np.matrix(np.real(distortion_tensor))

        except ValueError:
            raise MTex.MTpyError_Z('The array provided is not a proper' +
                                   'distortion tensor')

        try:
            DI = distortion_tensor.I
        except np.linalg.LinAlgError:
            raise MTex.MTpyError_Z('The provided distortion tensor is' +
                                   'singular - I cannot invert that!')

        # propagation of errors (using 1-norm) - step 1 - inversion of D:
        DI_err = np.zeros_like(distortion_err_tensor)

        # todo :include error on  determinant!!
        # D_det = np.linalg.det(distortion_tensor)

        dummy, DI_err = MTcc.invertmatrix_incl_errors(distortion_tensor,
                                                      distortion_err_tensor)

        # propagation of errors - step 2 - product of D.inverse and Z;
        # D.I * Z, making it 4 summands for each component:
        z_corrected = np.zeros_like(self.z)
        z_corrected_err = np.zeros_like(self.z_err)

        for idx_f in range(len(self.z)):
            z_corrected[idx_f] = np.array(np.dot(DI, np.matrix(self.z[idx_f])))
            for ii in range(2):
                for jj in range(2):
                    z_corrected_err[idx_f, ii, jj] = np.sum(np.abs(
                        np.array([DI_err[ii, 0] *
                                  self.z[idx_f, 0, jj],
                                  DI[ii, 0] *
                                  self.z_err[idx_f, 0, jj],
                                  DI_err[ii, 1] *
                                  self.z[idx_f, 1, jj],
                                  DI[ii, 1] *
                                  self.z_err[idx_f, 1, jj]])))

        return distortion_tensor, z_corrected, z_corrected_err

    def _get_only1d(self):
        """
        Return Z in 1D form.

        If Z is not 1D per se, the diagonal elements are set to zero,
        the off-diagonal elements keep their signs, but their absolute
        is set to the mean of the original Z off-diagonal absolutes.
        """

        z1d = copy.copy(self.z)

        for ii in range(len(z1d)):
            z1d[ii, 0, 0] = 0
            z1d[ii, 1, 1] = 0
            sign01 = np.sign(z1d[ii, 0, 1])
            sign10 = np.sign(z1d[ii, 1, 0])
            mean1d = 0.5 * (z1d[ii, 1, 0] + z1d[ii, 0, 1])
            z1d[ii, 0, 1] = sign01 * mean1d
            z1d[ii, 1, 0] = sign10 * mean1d

        return z1d

    only1d = property(_get_only1d,
                      doc=""" Return Z in 1D form. If Z is not 1D per se,
                              the diagonal elements are set to zero, the
                              off-diagonal elements keep their signs, but
                              their absolute is set to the mean of the
                              original Z off-diagonal absolutes.""")

    def _get_only2d(self):
        """
        Return Z in 2D form.

        If Z is not 2D per se, the diagonal elements are set to zero.
        """

        z2d = copy.copy(self.z)

        for ii in range(len(z2d)):
            z2d[ii, 0, 0] = 0
            z2d[ii, 1, 1] = 0

        return z2d

    only2d = property(_get_only2d,
                      doc="""Return Z in 2D form. If Z is not 2D per se,
                             the diagonal elements are set to zero. """)

    def _get_trace(self):
        """
        Return the trace of Z (incl. uncertainties).

        Returns
            -------------
            **tr** : np.ndarray(nfreq, 2, 2)
                    Trace(z)
            **tr_err** : np.ndarray(nfreq, 2, 2)
                       Error of Trace(z)

        """

        tr = np.array([np.trace(ii) for ii in self.z])

        tr_err = None
        if self.z_err is not None:
            tr_err = np.zeros_like(tr)
            tr_err[:] = self.z_err[:, 0, 0] + self.z_err[:, 1, 1]

        return tr, tr_err

    trace = property(_get_trace, doc='Trace of Z, incl. error')

    def _get_skew(self):
        """
        Return the skew of Z (incl. uncertainties).

        Returns
            -----------
            **skew**: np.ndarray(nfreq, 2, 2)
                    skew(z)
            **skew_err** : np.ndarray(nfreq, 2, 2)
                         Error of skew(z)

        """

        skew = np.array([ii[0, 1] - ii[1, 0] for ii in self.z])

        skewerr = None
        if self.z_err is not None:
            skewerr = np.zeros_like(skew)
            skewerr[:] = self.z_err[:, 0, 1] + self.z_err[:, 1, 0]

        return skew, skewerr

    skew = property(_get_skew, doc='Skew of Z, incl. error')

    def _get_det(self):
        """
        Return the determinant of Z (incl. uncertainties).

        Returns
                ----------
            **det_Z** : np.ndarray(nfreq)
                      det(z)
            **det_Z_err** : np.ndarray(nfreq)
                          Error of det(z)

        """

        det_Z = np.array([np.linalg.det(ii) for ii in self.z])

        det_Z_err = None
        if self.z_err is not None:
            det_Z_err = np.zeros_like(det_Z)
            det_Z_err[:] = np.abs(self.z[:, 1, 1] * self.z_err[:, 0, 0]) + \
                np.abs(self.z[:, 0, 0] * self.z_err[:, 1, 1]) + \
                np.abs(self.z[:, 0, 1] * self.z_err[:, 1, 0]) + \
                np.abs(self.z[:, 1, 0] * self.z_err[:, 0, 1])

        return det_Z, det_Z_err

    det = property(_get_det, doc='Determinant of Z, incl. error')

    def _get_norm(self):
        """
        Return the 2-/Frobenius-norm of Z (NO uncertainties yet).

        Returns
                ---------
            **znorm** : np.ndarray(nfreq)
                      norm(z)
            **znormerr** : np.ndarray(nfreq)
                         Error of norm(z)

        """

        znorm = np.array([np.linalg.norm(ii) for ii in self.z])
        znormerr = None

        if self.z_err is not None:
            znormerr = np.zeros_like(znorm)
            for idx, z_tmp in enumerate(self.z):
                value = znorm[idx]
                error_matrix = self.z_err[idx]
                radicand = 0.
                for ii in range(2):
                    for jj in range(2):
                        radicand += (error_matrix[ii, jj] *
                                     np.real(z_tmp[ii, jj])) ** 2
                        radicand += (error_matrix[ii, jj] *
                                     np.imag(z_tmp[ii, jj])) ** 2

                znormerr[idx] = 1. / value * np.sqrt(radicand)

        return znorm, znormerr

    norm = property(_get_norm, doc='Norm of Z, incl. error')

    def _get_invariants(self):
        """
        Return a dictionary of Z-invariants.

        Contains
                -----------
                        * z1
                        * det
                        * det_real
                        * det_imag
                        * trace
                        * skew
                        * norm
                        * lambda_plus/minus,
                        * sigma_plus/minus
        """

        invariants_dict = {}

        z1 = (self.z[:, 0, 1] - self.z[:, 1, 0]) / 2.
        invariants_dict['z1'] = z1

        invariants_dict['det'] = self.det[0]

        det_real = np.array([np.linalg.det(ii) for ii in np.real(self.z)])
        invariants_dict['det_real'] = det_real

        det_imag = np.array([np.linalg.det(ii) for ii in np.imag(self.z)])
        invariants_dict['det_imag'] = det_imag

        invariants_dict['trace'] = self.trace[0]

        invariants_dict['skew'] = self.skew[0]

        invariants_dict['norm'] = self.norm[0]

        lambda_plus = np.array([z1[ii] + np.sqrt(z1[ii] * z1[ii] -
                                                 self.det[0][ii]) for ii in range(len(z1))])
        invariants_dict['lambda_plus'] = lambda_plus

        lambda_minus = np.array([z1[ii] - np.sqrt(z1[ii] * z1[ii] -
                                                  self.det[0][ii]) for ii in range(len(z1))])
        invariants_dict['lambda_minus'] = lambda_minus

        sigma_plus = np.array([0.5 * self.norm[0][ii] ** 2 +
                               np.sqrt(0.25 * self.norm[0][ii] ** 4 +
                                       np.abs(self.det[0][ii]) ** 2)
                               for ii in range(len(self.norm[0]))])

        invariants_dict['sigma_plus'] = sigma_plus

        sigma_minus = np.array([0.5 * self.norm[0][ii] ** 2 -
                                np.sqrt(0.25 * self.norm[0][ii] ** 4 +
                                        np.abs(self.det[0][ii]) ** 2)
                                for ii in range(len(self.norm[0]))])
        invariants_dict['sigma_minus'] = sigma_minus

        return invariants_dict

    invariants = property(_get_invariants,
                          doc="""Dictionary, containing the invariants of
                                 Z: z1, det, det_real, det_imag, trace,
                                 skew, norm, lambda_plus/minus,
                                 sigma_plus/minus""")


# ======================================================================
#                               TIPPER
# ======================================================================

class Tipper(object):
    """
    Tipper class --> generates a Tipper-object.

    Errors are given as standard deviations (sqrt(VAR))

    Arguments
        -----------

        **tipper_array** : np.ndarray((nf, 1, 2), dtype='complex')
                          tipper array in the shape of [Tx, Ty]
                          *default* is None

        **tipper_err_array** : np.ndarray((nf, 1, 2))
                             array of estimated tipper errors
                               in the shape of [Tx, Ty].
                               Must be the same shape as tipper_array.
                               *default* is None

        **freq** : np.ndarray(nf)
                   array of frequencies corresponding to the tipper elements.
                   Must be same length as tipper_array.
                   *default* is None

    =============== ===========================================================
    Attributes      Description
    =============== ===========================================================
    freq            array of frequencies corresponding to elements of z
    rotation_angle  angle of which data is rotated by

    tipper          tipper array
    tipper_err       tipper error array
    =============== ===========================================================

    =============== ===========================================================
    Methods         Description
    =============== ===========================================================
    mag_direction   computes magnitude and direction of real and imaginary
                    induction arrows.
    amp_phase       computes amplitude and phase of Tx and Ty.
    rotate          rotates the data by the given angle
    =============== ===========================================================



    """

    def __init__(self, tipper_array=None, tipper_err_array=None,
                 freq=None):
        """
        Initialise an instance of the Tipper class.

        Arguments
                --------------

            **tipper_array** : np.ndarray((nf, 1, 2), dtype='complex')
                               tipper array in the shape of [Tx, Ty]
                               *default* is None

            **tipper_err_array** : np.ndarray((nf, 1, 2))
                                   array of estimated tipper errors
                                   in the shape of [Tx, Ty].
                                   Must be the same shape as tipper_array.
                                   *default* is None

            **freq** : np.ndarray(nf)
                       array of frequencies corresponding to the tipper
                       elements.
                       Must be same length as tipper_array.
                       *default* is None

        """

        self._tipper = tipper_array
        self._tipper_err = tipper_err_array
        self._freq = freq

        self.rotation_angle = 0.
        if self.tipper is not None:
            self.rotation_angle = np.zeros((len(self.tipper)))

        self.amplitude = None
        self.amplitude_err = None
        self._phase = None
        self._phase_err = None

        self.mag_real = None
        self.mag_imag = None
        self.angle_real = None
        self.angle_imag = None

        self.mag_err = None
        self.angle_err = None

    # ==========================================================================
    # Define get/set and properties
    # ==========================================================================
    # ----freq----------------------------------------------------------
    def _set_freq(self, lo_freq):
        """
        Set the array of freq.

        Arguments
                -----------

            **lo_freq** : list or array of frequnecies (Hz)

        No test for consistency!
        """

        if len(lo_freq) is not len(self.tipper):
            logger.info('length of freq list/array not correct' + \
                  ' (%ii instead of %ii)' % (len(lo_freq), len(self.tipper)))
            return

        self._freq = np.array(lo_freq)

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    def _get_freq(self):
        if self._freq is not None:
            self._freq = np.array(self._freq)
        return self._freq

    freq = property(_get_freq, _set_freq,
                    doc='array of freq')

    # ---tipper--------------------------------------------------------------
    def _set_tipper(self, tipper_array):
        """
        Set the attribute *tipper*

        Arguments
                -------------

            **tipper_array** : np.ndarray((nf, 1, 2), dtype='complex')
                               tipper array in the shape of [Tx, Ty]
                               *default* is None

        Test for shape, but no test for consistency!

        """
        # make sure the array is of required shape
        try:
            if len(tipper_array.shape) == 3 and tipper_array.shape[
                    1:3] == (1, 2):
                if tipper_array.dtype in ['complex', 'float', 'int']:
                    self._tipper = tipper_array
        except IndexError:
            pass

        # check to see if the new tipper array is the same shape as the old
        if (self._tipper is not None) and (
                self._tipper.shape != tipper_array.shape):
            logging.error( 'Error - shape of "tipper" array does not match shape of ' + \
                  'tipper-array: %s ; %s' % (str(tipper_array.shape),
                                             str(self.tipper.shape)))
            return

        self._tipper = tipper_array

        # neeed to set the rotation angle such that it is an array
        if self.rotation_angle is float:
            self.rotation_angle = np.repeat(self.rotation_angle,
                                            len(self._tipper))

            # for consistency recalculate mag and angle
        self._compute_mag_direction()

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    def _get_tipper(self):
        return self._tipper

    tipper = property(_get_tipper, _set_tipper, doc="Tipper array")

    # ----tipper error---------------------------------------------------------
    def _set_tipper_err(self, tipper_err_array):
        """
        Set the attribute *tipper_err*.

        Arguments
                --------------
            **tipper_err_array** : np.ndarray((nf, 1, 2))
                                   array of estimated tipper errors
                                   in the shape of [Tx, Ty].
                                   Must be the same shape as tipper_array.
                                   *default* is None

        Test for shape, but no test for consistency!

        """

        # make sure the input array is of required shape
        try:
            if len(tipper_err_array.shape) == 3 and \
                    tipper_err_array.shape[1:3] == (1, 2):
                if tipper_err_array.dtype in ['float', 'int']:
                    self._tipper_err = tipper_err_array
        except IndexError:
            pass

        # make sure the error array is the same shape as tipper
        try:
            if len(self.tipper) != len(self._tipper_err):
                self._tipper_err = None
        except TypeError:
            pass

        if (self.tipper_err is not None) and \
                (self._tipper_err.shape != tipper_err_array.shape):
            logging.error( 'Error - shape of "tipper_err" array does not match shape ' + \
                  'of tipper_err array: %s ; %s' % (str(tipper_err_array.shape),
                                                    str(self._tipper_err.shape)))
            return

        self._tipper_err = tipper_err_array

        # for consistency recalculate mag and angle
        self._compute_mag_direction()

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    def _get_tipper_err(self):
        return self._tipper_err

    tipper_err = property(_get_tipper_err, _set_tipper_err,
                          doc="Estimated Tipper errors")

    # ----real part---------------------------------------------------------
    def _get_real(self):
        """
        Return the real part of the Tipper.

        """
        if self.tipper is None:
            logging.error( 'tipper array is None - cannot calculate real')
            return

        return np.real(self.tipper)

    def _set_real(self, real_array):
        """
        Set the real part of 'tipper'.

        Arguments
                --------------

            **tipper_array** : np.ndarray((nf, 1, 2)) real part
                               tipper array in the shape of [Tx, Ty]
                               *default* is None

        Test for shape, but no test for consistency!

        """

        if (self.tipper is not None) and (
                self.tipper.shape != real_array.shape):
            logging.error( 'shape of "real" array does not match shape of tipper ' + \
                  'array: %s ; %s' % (str(real_array.shape), str(self.tipper.shape)))
            return

        # assert real array:
        if np.linalg.norm(np.imag(real_array)) != 0:
            logging.error( 'Error - array "real" is not real valued !')
            return

        if self.tipper is not None:
            tipper_new = real_array + 1j * self.imag()
        else:
            tipper_new = real_array

        self.tipper = tipper_new

        # for consistency recalculate mag and angle
        self._compute_mag_direction()

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    _real = property(_get_real, _set_real, doc='Real part of the Tipper')

    # ---imaginary part------------------------------------------------------
    def _get_imag(self):
        """
        Return the imaginary part of the Tipper.

        """

        if self.tipper is None:
            logging.error( 'tipper array is None - cannot calculate imag')
            return

        return np.imag(self.tipper)

    def _set_imag(self, imag_array):
        """
        Set the imaginary part of 'tipper'.

        Arguments
                --------------

            **tipper_array** : np.ndarray((nf, 1, 2)) imaginary part
                               tipper array in the shape of [Tx, Ty]
                               *default* is None

        Test for shape, but no test for consistency!

        """

        if (self.tipper is not None) and (
                self.tipper.shape != imag_array.shape):
            logging.error( 'shape of "real" array does not match shape of tipper ' + \
                  'array: %s ; %s' % (str(imag_array.shape),
                                      str(self.tipper.shape)))
            return

        # assert real array:
        if np.linalg.norm(np.imag(imag_array)) != 0:
            logging.error( 'Error - array "imag" is not real valued !')
            return

        ii_arr = np.complex(0, 1)
        if self.tipper is not None:
            tipper_new = self.real() + ii_arr * imag_array
        else:
            tipper_new = ii_arr * imag_array

        self.tipper = tipper_new

        # for consistency recalculate mag and angle
        self._compute_mag_direction()

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    _imag = property(_get_imag, _set_imag, doc='Imaginary part of the Tipper')

    # ----amplitude and phase
    def _compute_amp_phase(self):
        """
        Sets attributes
                        * *amplitude*
                        * *phase*
                        * *amplitude_err*
                        * *phase_err*

        values for resistivity are in in Ohm m and phase in degrees.
        """

        if self.tipper is None:
            # logging.error( 'tipper array is None - cannot calculate rho/phi')
            return None

        self.amplitude_err = None
        self._phase_err = None
        if self.tipper_err is not None:
            self.amplitude_err = np.zeros(self.tipper_err.shape)
            self._phase_err = np.zeros(self.tipper_err.shape)

        self.amplitude = np.zeros(self.tipper.shape)
        self._phase = np.zeros(self.tipper.shape)

        for idx_f in range(len(self.tipper)):
            for jj in range(2):
                self.amplitude[idx_f, 0, jj] = np.abs(
                    self.tipper[idx_f, 0, jj])
                self._phase[idx_f, 0, jj] = math.degrees(cmath.phase(
                    self.tipper[idx_f, 0, jj]))

                if self.tipper_err is not None:
                    r_err, phi_err = MTcc.propagate_error_rect2polar(
                        np.real(self.tipper[idx_f, 0, jj]),
                        self.tipper_err[idx_f, 0, jj],
                        np.imag(self.tipper[idx_f, 0, jj]),
                        self.tipper_err[idx_f, 0, jj])

                    self.amplitude_err[idx_f, 0, jj] = r_err
                    self._phase_err[idx_f, 0, jj] = phi_err

    def set_amp_phase(self, r_array, phi_array):
        """
        Set values for amplitude(r) and argument (phi - in degrees).

        Updates the attributes
                        * tipper
                        * tipper_err

        """

        if self.tipper is not None:

            tipper_new = copy.copy(self.tipper)

            if self.tipper.shape != r_array.shape:
                logging.error( 'Error - shape of "r" array does not match shape of ' + \
                      'tipper array: %s ; %s' % (str(r_array.shape),
                                                 str(self.tipper.shape)))
                return

            if self.tipper.shape != phi_array.shape:
                logging.error( 'Error - shape of "phi" array does not match shape of ' + \
                      'tipper array: %s ; %s' % (str(phi_array.shape),
                                                 str(self.tipper.shape)))
                return
        else:

            tipper_new = np.zeros(r_array.shape, 'complex')

            if r_array.shape != phi_array.shape:
                logging.error( 'Error - shape of "phi" array does not match shape ' + \
                      'of "r" array: %s ; %s' % (str(phi_array.shape),
                                                 str(r_array.shape)))
                return

        # assert real array:
        if np.linalg.norm(np.imag(r_array)) != 0:
            logging.error( 'Error - array "r" is not real valued !')
            return
        if np.linalg.norm(np.imag(phi_array)) != 0:
            logging.error( 'Error - array "phi" is not real valued !')
            return

        for idx_f in range(len(r_array)):
            for jj in range(2):
                tipper_new[idx_f, 0, jj] = cmath.rect(r_array[idx_f, 0, jj],
                                                      math.radians(phi_array[idx_f, 0, jj]))

        self.tipper = tipper_new

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()

    # ----magnitude and direction----------------------------------------------
    def _compute_mag_direction(self):
        """
        computes the magnitude and direction of the real and imaginary
        induction vectors.

        Returns
                ------------

            **mag_real** : np.array(nf)
                           magnitude of the real induction vector

            **ang_real** : np.array(nf)
                           angle (deg) of the real induction vector assuming
                           that North is 0 and angle is positive clockwise

            **mag_imag** : np.array(nf)
                           magnitude of the imaginary induction vector

            **ang_imag** : np.array(nf)
                           angle (deg) of the imaginary induction vector
                           assuming that North is 0 and angle is positive
                           clockwise


        """

        if self.tipper is None:
            return None
        self.mag_real = np.sqrt(self.tipper[:, 0, 0].real ** 2 +
                                self.tipper[:, 0, 1].real ** 2)
        self.mag_imag = np.sqrt(self.tipper[:, 0, 0].imag ** 2 +
                                self.tipper[:, 0, 1].imag ** 2)

        self.mag_err = None
        self.angle_err = None
        # get the angle, need to make both parts negative to get it into the
        # parkinson convention where the arrows point towards the conductor

        self.angle_real = np.rad2deg(np.arctan2(-self.tipper[:, 0, 1].real,
                                                -self.tipper[:, 0, 0].real))

        self.angle_imag = np.rad2deg(np.arctan2(-self.tipper[:, 0, 1].imag,
                                                -self.tipper[:, 0, 0].imag))

        # estimate error: THIS MAYBE A HACK
        if self.tipper_err is not None:
            self.mag_err = np.sqrt(self.tipper_err[:, 0, 0] ** 2 +
                                   self.tipper_err[:, 0, 1] ** 2)
            self.angle_err = np.rad2deg(np.arctan2(self.tipper_err[:, 0, 0],
                                                   self.tipper_err[:, 0, 1])) % 45

    def set_mag_direction(self, mag_real, ang_real, mag_imag, ang_imag):
        """
        computes the tipper from the magnitude and direction of the real
        and imaginary components.

        Updates tipper

        No error propagation yet
        """

        self.tipper[:, 0, 0].real = np.sqrt((mag_real ** 2 * np.arctan(ang_real) ** 2) /
                                            (1 - np.arctan(ang_real) ** 2))

        self.tipper[:, 0, 1].real = np.sqrt(mag_real ** 2 /
                                            (1 - np.arctan(ang_real) ** 2))

        self.tipper[:, 0, 0].imag = np.sqrt((mag_imag ** 2 * np.arctan(ang_imag) ** 2) /
                                            (1 - np.arctan(ang_imag) ** 2))

        self.tipper[:, 0, 1].imag = np.sqrt(mag_imag ** 2 /
                                            (1 - np.arctan(ang_imag) ** 2))
        # for consistency recalculate mag and angle
        self._compute_mag_direction()

    # ----rotate---------------------------------------------------------------
    def rotate(self, alpha):
        """
        Rotate  Tipper array.

        Rotation angle must be given in degrees. All angles are referenced
        to geographic North=0, positive in clockwise direction.
        (Mathematically negative!)

        In non-rotated state, 'X' refs to North and 'Y' to East direction.

        Updates the attributes
                        * *tipper*
                        * *tipper_err*
                        * *rotation_angle*

        """

        if self.tipper is None:
            logging.error( 'tipper array is "None" - I cannot rotate that')
            return

        # check for iterable list/set of angles - if so, it must have length 1
        # or same as len(tipper):
        if np.iterable(alpha) == 0:
            try:
                degreeangle = float(alpha % 360)
            except ValueError:
                logging.error( '"Angle" must be a valid number (in degrees)')
                return

            # make an n long list of identical angles
            lo_angles = [degreeangle for ii in self.tipper]
        else:
            if len(alpha) == 1:
                try:
                    degreeangle = float(alpha % 360)
                except ValueError:
                    logging.error( '"Angle" must be a valid number (in degrees)')
                    return
                # make an n long list of identical angles
                lo_angles = [degreeangle for ii in self.tipper]
            else:
                try:
                    lo_angles = [float(ii % 360) for ii in alpha]
                except ValueError:
                    logging.error( '"Angles" must be valid numbers (in degrees)')
                    return

        self.rotation_angle = np.array([(oldangle + lo_angles[ii]) % 360
                                        for ii, oldangle in enumerate(self.rotation_angle)])

        if len(lo_angles) != len(self.tipper):
            logging.error( 'Wrong number Number of "angles" - need %ii ' % (len(self.tipper)))
            self.rotation_angle = 0.
            return

        tipper_rot = copy.copy(self.tipper)
        tipper_err_rot = copy.copy(self.tipper_err)

        for idx_freq in range(len(tipper_rot)):
            angle = lo_angles[idx_freq]

            if self.tipper_err is not None:
                tipper_rot[idx_freq], tipper_err_rot[idx_freq] = \
                    MTcc.rotatevector_incl_errors(self.tipper[idx_freq, :, :],
                                                  angle,
                                                  self.tipper_err[idx_freq, :, :])
            else:
                tipper_rot[idx_freq], tipper_err_rot = \
                    MTcc.rotatevector_incl_errors(self.tipper[idx_freq, :, :],
                                                  angle)

        self.tipper = tipper_rot
        self.tipper_err = tipper_err_rot

        # for consistency recalculate mag and angle
        self._compute_mag_direction()

        # for consistency recalculate amplitude and phase
        self._compute_amp_phase()


# ------------------------
def correct4sensor_orientation(Z_prime, Bx=0, By=90, Ex=0, Ey=90,
                               Z_prime_error=None):
    """
    Correct a Z-array for wrong orientation of the sensors.

    Assume, E' is measured by sensors orientated with the angles
        E'x: a
        E'y: b

    Assume, B' is measured by sensors orientated with the angles
        B'x: c
        B'y: d

    With those data, one obtained the impedance tensor Z':
        E' = Z' * B'

    Now we define change-of-basis matrices T,U so that
        E = T * E'
        B = U * B'

    =>   T contains the expression of the E'-basis in terms of E
    (the standard basis)
    and  U contains the expression of the B'-basis in terms of B
    (the standard basis)
    The respective expressions for E'x-basis vector and E'y-basis
    vector are the columns of T.
    The respective expressions for B'x-basis vector and B'y-basis
    vector are the columns of U.

    We obtain the impedance tensor in default coordinates as:

    E' = Z' * B' => T^(-1) * E = Z' * U^(-1) * B
                 => E = T * Z' * U^(-1) * B
                 => Z = T * Z' * U^(-1)


    Arguments
        ---------------
                **Z_prime** : np.ndarray(num_freq, 2, 2, dtype='complex')
                                          impedance tensor to be adjusted

                **Bx** : float (angle in degrees)
                         orientation of Bx relative to geographic north (0)
                                 *default* is 0
                **By** : float (angle in degrees)
                         orientation of By relative to geographic north (0)
                                 *default* is 90
                **Ex** : float (angle in degrees)
                         orientation of Ex relative to geographic north (0)
                                 *default* is 0
                **Ey** : float (angle in degrees)
                         orientation of Ey relative to geographic north (0)
                                 *default* is 90

                Z_prime_error : np.ndarray(Z_prime.shape)
                                impedance tensor error (std)
                                                *default* is None

        Returns
        -------------
                **Z** : np.ndarray(Z_prime.shape, dtype='complex')
                        adjusted impedance tensor

                **Z_err** : np.ndarray(Z_prime.shape, dtype='real')
                            impedance tensor standard deviation in
                                        default orientation


    """
    try:
        if len(Z_prime.shape) != 2:
            raise
        if Z_prime.shape != (2, 2):
            raise

        if Z_prime.dtype not in ['complex', 'float', 'int']:
            raise

        Z_prime = np.matrix(Z_prime)

    except:
        raise MTex.MTpyError_inputarguments('ERROR - Z array not valid!' +
                                            'Must be 2x2 complex array')

    if Z_prime_error is not None:
        try:
            if len(Z_prime_error.shape) != 2:
                raise
            if Z_prime_error.shape != (2, 2):
                raise

            if Z_prime_error.dtype not in ['float', 'int']:
                raise

        except:
            raise MTex.MTpyError_inputarguments('ERROR - Z-error array not' +
                                                'valid! Must be 2x2 real array')

    T = np.matrix(np.zeros((2, 2)))
    U = np.matrix(np.zeros((2, 2)))

    dummy1 = cmath.rect(1, math.radians(Ex))

    T[0, 0] = np.real(dummy1)
    T[1, 0] = np.imag(dummy1)
    dummy2 = cmath.rect(1, math.radians(Ey))
    T[0, 1] = np.real(dummy2)
    T[1, 1] = np.imag(dummy2)

    dummy3 = cmath.rect(1, math.radians(Bx))
    U[0, 0] = np.real(dummy3)
    U[1, 0] = np.imag(dummy3)
    dummy4 = cmath.rect(1, math.radians(By))
    U[0, 1] = np.real(dummy4)
    U[1, 1] = np.imag(dummy4)

    try:
        z_arr = np.array(np.dot(T, np.dot(Z_prime, U.I)))
    except:
        raise MTex.MTpyError_inputarguments("ERROR - Given angles do not" +
                                            "define basis for 2 dimensions - cannot convert Z'")

    z_err_arr = copy.copy(Z_prime_error)

    # TODO: calculate error propagation

    return z_arr, z_err_arr
