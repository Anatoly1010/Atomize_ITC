# Insys acquisition protection

Development branch: `dev`. Linux FPGA validation is pending. The queue feature is committed independently on `master`; user-facing FPGA documentation belongs to `atomize_docs` on its matching `dev` branch.

## Behavior

ITC checks FPGA availability before script testing and immediately before launch, including cached or disabled tests and queue advancement. A refusal preserves waiting queue entries. The driver repeats the availability check in real `pulser_open()`, so scripts using this installation also receive protection outside the GUI.

Test mode never claims or releases the FPGA. Failed-test handling no longer writes `Status: Off`. Real initialization records ownership before calling the vendor library. A rejected driver instance cannot close the board or clear another owner's record.

The driver marks the board open immediately after successful `initBrd()`, allowing caller `finally` blocks to clean up if later configuration fails. Initialization failure before success is uncertain and requires reboot. Cleanup attempts every shutdown step; a reported failure preserves the busy record and requires reboot. Successful cleanup clears only the matching owner's record. Repeated successful closing is a no-op. If writing Off fails after successful board release, the owner can retry that write without repeating hardware cleanup. A separate completed-release flag distinguishes this case from a Stop handler interrupting initialization; the latter must not clear ownership before release has been established.

## Status and recovery

`atomize/general_modules/insys_status.py` uses this installation's `libs/status`, independent of the working directory. The first line remains `Status:  On` or `Status:  Off`. Busy records add PID, process start ticks, boot UUID, and a driver-instance token. A failed cleanup adds `Recovery:  Required` while keeping the first line On.

Availability reads never modify status. Missing status means no recorded owner; unreadable or malformed status blocks launch. A living matching process remains busy, including after its GUI disappears. A dead or zombie process, reused PID, or explicit recovery marker blocks acquisition until reboot. There is no automatic reset or status-clearing workaround for an unreleased FPGA.

The Linux boot UUID comes from `/proc/sys/kernel/random/boot_id`; process state and start ticks come from `/proc/<pid>/stat`. A different boot UUID invalidates the old record. Legacy On records without ownership information remain blocked unless their file timestamp predates `/proc/stat`'s boot time. Real claims require Linux identity information; Windows remains suitable for mocked checks and read-only test mode.

Status updates use a flushed temporary file and atomic replacement to prevent partial records. This does not make checking and claiming one indivisible operation: simultaneous acquisition starts remain outside this correction's guarantee. The existing field/temperature locks and RECT/AWG worker protocol are unchanged.

Linux reference: [kernel boot UUID](https://docs.kernel.org/admin-guide/sysctl/kernel.html#random) and [proc filesystem](https://docs.kernel.org/filesystems/proc.html).

## Vendor return values verified from the supplied binary

The available wrapper description declares integer returns without defining their meaning. Static disassembly of the shipped `libs/libNvsbLib.so` established these return paths without executing the library:

| Export | Normal return | Relevant binary address |
| --- | --- | --- |
| `initBrd` | 2 | `0xa8a3` sets `ebx = 2`, common return at `0xa70b` |
| `closeBrd` | 2 | `0xa9d9` sets `eax = 2` |
| `setZero_GIM`, `rst_GIM`, `setSync_GIM` | 1 | Normal paths return 1 |
| `setEnable_GIM`, `setDACEnable_GIM`, `setSwitchEn_GIM` | 1 | Normal paths return 1 |

SHA-256: `b713f2f134da18cc940157aa5db3265e9b45b744a5bb96b92e6900ecfdc05581`.

`initBrd` has negative error returns; `closeBrd` and the listed setters return -498 when their internal board object is missing. Python checks the normal return values and propagates failures. The wrapper does not propagate every internal vendor-call result, so its normal return cannot independently prove physical board release. This contract must be reviewed if the wrapper library is replaced. No disassembler dependency was added to the project.

## Validation

`python -B -m pytest tests/test_insys_guard.py tests/test_control_stop.py -q -p no:cacheprovider`: 76 passed on Windows with mocked board calls and Linux process identities. The updated `atomize_docs` pages also passed `mkdocs build --strict`.

Coverage includes read-only successful/incorrect/rejected tests, disabled and cached tests, queued launches, occupancy beginning during preflight, idle phasing windows, failed-test status preservation, owner-only cleanup, return-code and exception failures, PID reuse, zombie/dead owners, reboot recovery, legacy status, canonical paths, and failed status writes before initialization.

Live verification on the Linux spectrometer is still required for normal opening, Stop and closing with the supplied wrapper. Crash and failed-cleanup behavior were simulated; the real FPGA was not deliberately stranded.

## Real DEER script termination review

The requested example is `atomize/script_examples/EPR_endstation/Pulsed_EPR/AWG/DEER/0_deer_for_test.py`. Tests execute that source unchanged with simulated devices and invoke its registered SIGTERM callback directly; they do not send signals to hardware processes.

| Exit path | Current script behavior | FPGA status consequence |
| --- | --- | --- |
| Normal completion | Calls `pb.pulser_close()` after the acquisition loops | Off after successful cleanup |
| Main-panel Stop on Linux | SIGTERM handler closes FPGA, then attempts data saving | Off after successful cleanup; saving raises `NameError` because `file_data` is never assigned |
| Exception after opening | No surrounding `try/finally` closes the board | Remains On; process death requires reboot |
| Ctrl+C | Only SIGTERM has a custom handler; `KeyboardInterrupt` has no cleanup path | Remains On; process death requires reboot |
| Stop during initialization | Cleanup can run before `pulser_open()` has established a successful open | Uncertain release remains blocked and requires reboot |

The cleanup handler is registered before `data` and `header` are defined, so early Stop can also encounter missing save variables. The file-dialog assignment and normal final save call are commented out. The FPGA guard does not add exception handling or data saving to user scripts, and this review does not change the experiment's pulse settings or source.

Before using this example as a live validation script, its acquisition should be enclosed in `try/finally`, its save path made explicit or the save step omitted, and SIGTERM/Ctrl+C routed through one cleanup path. These are script-level findings, separate from the driver protection committed here.
