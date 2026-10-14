"""
Synthetic workflow for testing Liveplot pinning, floating plots and Layout presets.

Plots appear in stages (every plot updates about every 0.5 s):
  0 s  'Demo echo', 'Demo FID'      15 s  'Demo map' (2D, row by row)
  5 s  'Demo field sweep'           20 s  'Demo extra 1', 'Demo extra 2'
 10 s  'Demo baseline'              40 s  'Demo FID' stops updating (idle)
The script ends by itself after 90 s.

Manual test:
1. Pin 'Demo echo' and 'Demo FID' in the first 5 s and arrange them by hand.
2. Float one plot (double-click its title bar).
3. Watch new plots appear without the pinned or floating ones moving.
4. Try each Layout preset, also after 20 s when more than 4 plots are shown.
5. Run the script a second time and check that pins and arrangement survive.
"""

import numpy as np
import atomize.general_modules.general_functions as general

STEP_S = 0.5
TOTAL_STEPS = 180
FIELD_STAGE, BASELINE_STAGE, MAP_STAGE, EXTRA_STAGE, FID_STOP = 10, 20, 30, 40, 80

POINTS = 500
MAP_ROWS = 60
time_axis = np.linspace(0, 2000, POINTS)
field_axis = np.linspace(3400, 3600, POINTS)
map_data = np.zeros((POINTS, MAP_ROWS))

def noise(scale=0.05):
    return scale * np.random.normal(size=POINTS)

general.message('Demo: echo and FID started')

for step in range(TOTAL_STEPS):
    phase = 0.1 * step

    echo = np.exp(-((time_axis - 1000) / 120) ** 2)
    general.plot_1d('Demo echo', time_axis, (echo * np.cos(phase) + noise(), echo * np.sin(phase) + noise()),
                    label='echo', xname='Time', xscale='ns', yname='Signal', yscale='V')

    if step < FID_STOP:
        fid = np.exp(-time_axis / 400) * np.cos(time_axis / 40 + phase)
        general.plot_1d('Demo FID', time_axis, fid + noise(), label='FID',
                        xname='Time', xscale='ns', yname='Signal', yscale='V')
    elif step == FID_STOP:
        general.message('Demo: FID stopped updating (should turn idle)')

    if step >= FIELD_STAGE:
        if step == FIELD_STAGE:
            general.message('Demo: field sweep appeared')
        center = 3500 + 10 * np.sin(phase)
        line = -2 * (field_axis - center) / 25 * np.exp(-((field_axis - center) / 25) ** 2)
        general.plot_1d('Demo field sweep', field_axis, line + noise(), label='CW',
                        xname='Field', xscale='G', yname='Intensity', yscale='V')

    if step >= BASELINE_STAGE:
        if step == BASELINE_STAGE:
            general.message('Demo: baseline appeared')
        general.plot_1d('Demo baseline', time_axis, 0.02 * np.sin(time_axis / 300 + phase) + noise(0.01),
                        label='baseline', xname='Time', xscale='ns', yname='Signal', yscale='V')

    if step >= MAP_STAGE:
        row = step - MAP_STAGE
        if row == 0:
            general.message('Demo: 2D map appeared')
        if row < MAP_ROWS:
            map_data[:, row] = np.exp(-time_axis / (300 + 10 * row)) + noise()
            general.plot_2d('Demo map', map_data, start_step=((0, time_axis[1]), (3400, 200 / MAP_ROWS)),
                            xname='Time', xscale='ns', yname='Field', yscale='G', zname='Signal', zscale='V')
        elif row == MAP_ROWS:
            general.message('Demo: 2D map complete')

    if step >= EXTRA_STAGE:
        if step == EXTRA_STAGE:
            general.message('Demo: extra 1 and extra 2 appeared (more than 4 plots)')
        for k, name in enumerate(('Demo extra 1', 'Demo extra 2')):
            general.plot_1d(name, time_axis, np.sin(time_axis / (100 + 50 * k) + phase) + noise(),
                            label=name, xname='Time', xscale='ns', yname='Signal', yscale='V')

    general.wait(f'{STEP_S} s')

general.message('Demo: finished after 90 s')
