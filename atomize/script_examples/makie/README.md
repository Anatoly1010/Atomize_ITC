# Atomize → Julia/Makie publication figures

Turn Atomize CSV exports (Data Treatment, control-center tools) into
publication-quality figures with [Makie](https://docs.makie.org). Atomize CSVs
carry their column names + units in a `#`-comment header, so axis labels can be
read straight from the file.

## Files

- `atomize_makie.jl` — the helper module (`read_atomize`, `iq`, `theme_pub`,
  `pub_axis`, `palette_n`, `load_glob`, `autolabel!`, `plot_atomize`).
- `render.jl` — CLI: `julia render.jl <out.pdf|svg|png> <in.csv> [more.csv …]`.
  Used by the Data Treatment **“Makie figure…”** button.
- `Project.toml` — this folder is its own Julia environment, so deps are pinned
  and your global env is left alone.

## One-time setup

```bash
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
```

(The first run is slow — CairoMakie precompiles once. Later runs still pay
~15 s of Julia + CairoMakie startup per render, since each call is a fresh
process. To make renders near-instant, bake a sysimage with PackageCompiler.jl
or keep a Julia server alive with DaemonMode.jl.)

## From the GUI

In the 1D Data Treatment window, pick what to draw in the dropdown next to the
button — **Raw + result** (overlay, e.g. fit over its data), **Result only**, or
**Raw only** — then click **“Makie figure…”** and choose an output name
(`.pdf` default → vector). The selected curves are written to temp CSV(s) and
rendered by `render.jl` in a background process; the PDF opens when done.
Curves that share an X axis go into one figure with a column legend; curves on
different X axes (e.g. a time-domain source and a frequency-domain result) are
overlaid as separate inputs.

## From a notebook / script

```julia
include("atomize_makie.jl"); using .AtomizeMakie
set_theme!(theme_pub())

# one call — auto-labels axes from the CSV header
save("trace.pdf", plot_atomize("trace.csv"))

# a whole sweep folder, haline palette + filename legend
traces = load_glob("sweep_dir"); pal = palette_n(length(traces))
fig = Figure(); ax = pub_axis(fig[1,1])
for (i,t) in enumerate(traces)
    lines!(ax, t.data[:,1], t.data[:,2]; color=pal[i], label=replace(t.name,".csv"=>""))
end
autolabel!(ax, traces[1].names)        # xlabel/ylabel from the header
axislegend(ax; framevisible=false); fig

# phased I/Q:  real((I + im*Q)·e^{iφ})
lines!(ax, t.data[:,1], real(iq(t.data; phase=0.1)))
```
