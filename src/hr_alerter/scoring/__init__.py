"""Scoring sub-package for the hr-alerter project.

Exports the composite scorer so other modules can do::

    from hr_alerter.scoring import calculate_final_score
"""

from hr_alerter.scoring.composite import calculate_final_score

__all__ = ["calculate_final_score"]
