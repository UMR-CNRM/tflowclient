# -*- coding: utf-8 -*-

#  Copyright (©) Meteo-France (2020-)
#
#  This software is a computer program whose purpose is to provide
#   a text-based console client to interact with various workflow schedulers.
#
#  This software is governed by the CeCILL-C license under French law and
#  abiding by the rules of distribution of free software.  You can  use,
#  modify and/ or redistribute the software under the terms of the CeCILL-C
#  license as circulated by CEA, CNRS and INRIA at the following URL
#  "http://www.cecill.info".
#
#  As a counterpart to the access to the source code and  rights to copy,
#  modify and redistribute granted by the license, users are provided only
#  with a limited warranty  and the software's author,  the holder of the
#  economic rights,  and the successive licensors  have only  limited
#  liability.
#
#  In this respect, the user's attention is drawn to the risks associated
#  with loading,  using,  modifying and/or developing or reproducing the
#  software by the user in light of its specific status of free software,
#  that may mean  that it is complicated to manipulate,  and  that  also
#  therefore means  that it is reserved for developers  and  experienced
#  professionals having in-depth computer knowledge. Users are therefore
#  encouraged to load and test the software's suitability as regards their
#  requirements in conditions enabling the security of their systems and/or
#  data to be ensured and,  more generally, to use and operate it in the
#  same conditions as regards security.
#
#  The fact that you are presently reading this means that you have had
#  knowledge of the CeCILL-C license and that you accept its terms.

"""
A very crude implementation of the observer design pattern.
"""

from __future__ import annotations

import weakref

__all__ = ["Subject", "Observer"]


class Subject(object):
    """Mixin class for any Observable class."""

    def __init__(self):
        """
        No required arguments.
        """
        self._observers = weakref.WeakSet()

    def observer_attach(self, observer: Observer):
        """Attach a new :class:`Observer` object to this class."""
        assert isinstance(observer, Observer)
        self._observers.add(observer)

    def observer_detach(self, observer: Observer):
        """Remove an :class:`Observer` object form the observers list to this class."""
        assert isinstance(observer, Observer)
        self._observers.discard(observer)

    def _notify(self, info: dict):
        """Notify all of the attached :class:`Observer` object."""
        for observer in self._observers:
            observer.update_obs_item(self, info)


class Observer(object):
    """Abstract class for any observer class."""

    def update_obs_item(self, item: Subject, info: dict):
        """Process the ***info** update triggered by the **item** object."""
        raise NotImplementedError()
