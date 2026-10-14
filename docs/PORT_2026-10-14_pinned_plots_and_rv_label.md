# Port note — session 2026-10-14: pinned Liveplot plots and the Rotary Vane highlight

Two GUI fixes made in Atomize_ITC that apply to other Atomize versions with the same files.
Apply them by hand (context may differ between versions); the diffs below show the change
made in Atomize_ITC. Delete this file once the fixes are ported.

## 1. Liveplot: pinned plots stay visible and the grid keeps its layout (`atomize/main/main_window.py`)

- Every new data source (for example Run Pulses after Stop) called `begin_run`, which switched
  Grid off and followed the new run: pinned plots were hidden. Now `begin_run` leaves a Grid view
  alone, and the run-following view also shows pinned plots.
- `refresh_view` re-added every visible dock on each call, which reset the splitter sizes set by
  hand. It now re-adds them only when the set of visible plots changes.

Checked on the spectrometer: four pinned plots keep their grid positions across Stop / Run Pulses.

```diff
diff --git a/atomize/main/main_window.py b/atomize/main/main_window.py
index 688b297..13c6996 100644
--- a/atomize/main/main_window.py
+++ b/atomize/main/main_window.py
@@ -1149,6 +1149,7 @@ class NameList(QDockWidget):
         self.idle_timer.timeout.connect(self.refresh_idle_plots)
         self.idle_timer.start()
         self.pinned = set()
+        self.last_visible = []
         self.run_source = None
         self.run_plots = None
         self.following_run = False
@@ -1254,9 +1255,10 @@ class NameList(QDockWidget):
         items[0].setToolTip('\n'.join(status))
 
     def begin_run(self, source=None):
-        self.grid_button.setChecked(False)
         self.run_source = source
         self.run_plots = set()
+        if self.grid_button.isChecked():
+            return
         self.finished_plots.clear()
         self.following_run = True
         self.namelist_view.selectionModel().clear()
@@ -1325,7 +1327,7 @@ class NameList(QDockWidget):
         active = {name for name in self.plot_dict if self.plot_sources.get(name)}
         following = self.following_run and not self.grid_button.isChecked()
         if following:
-            wanted = active | self.finished_plots
+            wanted = active | self.finished_plots | self.pinned
         elif not self.grid_button.isChecked():
             wanted = self.pinned | {current}
         else:
@@ -1342,11 +1344,14 @@ class NameList(QDockWidget):
                 for dock in docks:
                     if dock.parent() is not None and dock.area is not self.hidden_area:
                         self.hidden_area.addDock(dock)
-        for position, dock in enumerate(visible):
-            if len(visible) > 2 and position % 2:
-                self.window.dockarea.addDock(dock, position='right', relativeTo=visible[position - 1])
-            else:
-                self.window.dockarea.addDock(dock, position='bottom')
+        # re-adding docks resets the splitter sizes, so keep an unchanged layout as the user arranged it
+        if visible != self.last_visible or any(dock.area is not self.window.dockarea for dock in visible):
+            for position, dock in enumerate(visible):
+                if len(visible) > 2 and position % 2:
+                    self.window.dockarea.addDock(dock, position='right', relativeTo=visible[position - 1])
+                else:
+                    self.window.dockarea.addDock(dock, position='bottom')
+        self.last_visible = visible
         self.pin_button.setEnabled(current in self.plot_dict)
         self.show_run_button.setEnabled(bool(active))
         self.show_run_button.setChecked(bool(active) and following and shown == active)
```

## 2. MW bridge window: the Rotary Vane label turns red while the vane moves (`atomize/control_center/mw_bridge_control.py`)

The label was coloured red and back from a background thread while the window thread was blocked
waiting for the bridge reply (up to 1 s). For short moves the highlight came and went before the
window could repaint, so it never showed. The window now paints the label itself (`repaint()`)
and clears it with a single-shot `QTimer` after the move time; the pacing thread only waits.

Checked on the spectrometer: the label turns red while the vane moves.

```diff
diff --git a/atomize/control_center/mw_bridge_control.py b/atomize/control_center/mw_bridge_control.py
index 4ab6038..d026b68 100644
--- a/atomize/control_center/mw_bridge_control.py
+++ b/atomize/control_center/mw_bridge_control.py
@@ -50,6 +50,10 @@ class MainWindow(QMainWindow):
 
         self.design()
 
+        self.label_timer = QTimer(self)
+        self.label_timer.setSingleShot(True)
+        self.label_timer.timeout.connect(lambda: self.label_1.setStyleSheet(REFINED_STYLES['LABEL_STYLE']))
+
         self.curr_dB = 60
         self.prev_dB = 60
         self.p1 = 'None'
@@ -680,10 +684,11 @@ class MainWindow(QMainWindow):
 
         #self.telemetry_text.appendPlainText( 'Frequency: ' + freq )
 
-    def pause_and_label(self, time):
+    def show_vane_moving(self, ms):
+        # painted here because the window is busy waiting for the bridge reply while the vane turns
         self.label_1.setStyleSheet("QLabel { color : rgb(255, 0, 0); font-weight: bold; }")
-        general.wait( time )
-        self.label_1.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])
+        self.label_1.repaint()
+        self.label_timer.start(int(ms))
     
     def pause_and_label_exit(self, time):
         general.wait( time )
@@ -715,7 +720,8 @@ class MainWindow(QMainWindow):
         # 36 is a manual calibration
         time_to_wait = abs( 36 * step )
 
-        self.p1 = Thread(target = self.pause_and_label, args = (str(time_to_wait) + ' ms', ) )
+        self.show_vane_moving(time_to_wait)
+        self.p1 = Thread(target = self.pause_and_label_exit, args = (str(time_to_wait) + ' ms', ) )
         self.p1.start()
         
         data_raw = self._recv(6)
@@ -791,7 +797,8 @@ class MainWindow(QMainWindow):
         MESSAGE = b'\x0e' + b'\x04' + b'\x01' + b'\x01' + (3).to_bytes( 2, byteorder = 'big', signed = False )
         self.sock.sendto( MESSAGE, (self.UDP_IP, self.UDP_PORT) )
 
-        self.p1 = Thread(target = self.pause_and_label, args = ( '5 s', ) )
+        self.show_vane_moving(5000)
+        self.p1 = Thread(target = self.pause_and_label_exit, args = ( '5 s', ) )
         self.p1.start()
         
         data_raw = self._recv(6)
```
