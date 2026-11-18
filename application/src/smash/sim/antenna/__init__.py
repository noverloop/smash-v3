"""Sleeve-antenna FDTD study (openEMS) — printed HF slots on the LDS sleeve.

  geometry.build_tower(...) → TowerModel (pure Python, from generator constants)
  cases.option_model("A"|"B"|"C") → the three slot options under comparison
  geometry.model_to_dict(model) → JSON consumed by openems_runner
  openems_runner.py → runs inside the `smash-openems` container
  python -m smash.sim.antenna <case> → build JSON, run in Docker, summarise

openEMS is not packaged for macOS (and Debian only ships a 2019 build), so it
runs from a source-built image:  docker build -t smash-openems
application/src/smash/sim/antenna/docker
"""
