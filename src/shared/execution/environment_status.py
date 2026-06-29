from enum import Enum


class EnvironmentStatus(Enum):
    """
    EnvironmentStatus represents the lifecycle of an execution environment.
    """

    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    CLEANING = "CLEANING"
    RELEASED = "RELEASED"
