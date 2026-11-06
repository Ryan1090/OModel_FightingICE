"""Independent, data-derived move-table validator. Development version."""
__version__='0.1.0-dev'


def validate(candidate_motion_csv,base_character,*,mode='full',budget_seconds=50):
    from .api import validate as run
    return run(candidate_motion_csv,base_character,mode=mode,budget_seconds=budget_seconds)
