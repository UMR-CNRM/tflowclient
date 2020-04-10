# -*- coding: utf-8 -*-

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
