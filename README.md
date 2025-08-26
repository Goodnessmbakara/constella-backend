# Tutils

## AGI Parts

1. Sensors (with overlap to actuators)

-   The connections to the real world
-   Seeing data, interacting with it, all the inputs

2. Actuators

-   Ability to act on things
-   Related to the sensors

3. Thinking

-   The reasoning behind actions and then doing them

4. Running

-   The infra on which to run
-   Auto-loops / background tasks / automations
-   Learning and loops

## Production Deploy Checklist

1. Make sure no `TODO: delete`
2. Make sure no `TODO: uncomment`

## Setting UP

**Important: ** Python version: Python 3.10.9. The 3.13 does not work due to library updates.

Use this version when creating the venv below.

1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `uvicorn main:app --reload`
5. Please create separate branches for all tasks and always avoid merging directly to main.

**Warning: ** Main is directly connected to production server (itzerhyper)

** NOTE: ** Before deploying to production, make sure to add the new environment variables and test on staging first.

Backend for all my side projects until they become too big to be managed by one backend.

## Comments

-   `TODO`: future work
    -   `TODO: DELETE`: make sure to remove these from the pr
-   `IMPROV`: improvements
