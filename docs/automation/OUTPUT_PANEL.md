# Optional shared Output panel

Output starts below the Script Editor on the Main tab, as before.

- Check **Shared** in the Output header to keep the same log visible on Main,
  Liveplot, and EPR Endstation Control. Uncheck it to return Output to Main.
- Click **→** to move Output to the right, or **↓** to move it below.
- Drag the divider to resize the panel.
- Shared Output has 8 px of outer spacing, with no extra space next to the divider.
- **Auto-scroll** follows the latest message, including after moving or resizing
  Output. It is enabled when Atomize starts.
- Scroll up to pause Auto-scroll and read older messages. Your reading position
  is preserved when messages arrive or the panel moves. Scroll to the bottom,
  press **Ctrl+End**, or check Auto-scroll to resume following.

Output cannot be hidden. With Shared unchecked, it remains on Main; with Shared
checked, it is visible on every tab. Changing the layout does not clear the log
or affect running scripts and protocols. Sharing, placement, and separate divider
sizes for each layout are remembered in `workspace.ini` beside the user
configuration. Any previously saved hidden state is discarded.

The shared `main_window.py` installs this layout through `output_panel.py` in
Atomize, ITC, NIOCH, NIOCH_Q, and Cryomech. Each version saves its preferences
beside its own main configuration. Existing log handlers are unchanged.

## Manual check

1. Start Atomize and check that the initial Main layout is familiar.
2. Check Shared, open Liveplot, and try both Output positions. Resize the divider.
3. Open EPR Endstation Control and run a protocol with Dry run checked. Confirm
   that progress is visible alongside the controls and on Liveplot.
4. With enough messages to scroll, move Output between bottom and right. With
   Auto-scroll checked, the newest message should remain visible.
5. Scroll up, move the panel again, and let new messages arrive. The same older
   text should stay in view. Check Auto-scroll to return to the latest message.
6. Uncheck Shared and confirm Output returns to Main.
7. Restart Atomize and check that the chosen layout and panel size are restored.
