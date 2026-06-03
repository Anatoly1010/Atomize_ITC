# atomize_makie.jl — turn Atomize CSV exports into publication figures (CairoMakie).
#
#   include("atomize_makie.jl")
#   using .AtomizeMakie
#
# Atomize's Data Treatment / control-center tools save CSV as:
#       # meta line 1
#       # meta line 2
#       # Time (ns), Real, Imag        <- last comment line = column names
#       1.000000e+00,2.000000e+00,3.000000e+00
#       ...
# so the column NAMES + UNITS already live in the file. This module reads them,
# auto-skips the (variable-length) header — no more hardcoded skipstart=25 — and
# gives you a publication theme + axis helper that match the look you already use.

module AtomizeMakie

using DelimitedFiles, CairoMakie, LaTeXStrings, ColorSchemes, Colors

export read_atomize, iq, theme_pub, pub_axis, palette_n, load_glob,
       autolabel!, plot_atomize

# ---------------------------------------------------------------------------
# IO: read an Atomize CSV, returning (data::Matrix, names::Vector{String}).
# Header rows (leading "#"-comment lines AND any non-numeric preamble) are
# auto-detected, so the same call works whether a file has 3 or 25 header lines.
# ---------------------------------------------------------------------------
function read_atomize(path::AbstractString)
    lines = readlines(path)
    comments = filter(l -> startswith(lstrip(l), "#"), lines)
    # column names = last comment line, stripped of "# " and split on commas
    names = String[]
    if !isempty(comments)
        raw = strip(replace(last(comments), r"^\s*#+\s*" => ""))
        names = strip.(split(raw, ","))
    end
    # find the first line that parses as comma-separated floats -> data start
    isnum(s) = !isnothing(tryparse(Float64, strip(s)))
    start = findfirst(l -> !isempty(strip(l)) &&
                            !startswith(lstrip(l), "#") &&
                            all(isnum, split(l, ",")), lines)
    start === nothing && error("no numeric data found in $path")
    data = readdlm(path, ',', Float64; skipstart = start - 1)
    return data, names
end

# Combine I/Q columns into a phased complex signal: real(iq(tr; phase=φ)) is your
# usual `real((tr[:,2] + 1im*tr[:,3]) * exp(1im*φ))`. cols defaults to (2,3).
iq(data::AbstractMatrix; phase::Real = 0.0, cols = (2, 3)) =
    (data[:, cols[1]] .+ 1im .* data[:, cols[2]]) .* exp(1im * phase)

# Colorblind-safe categorical palette (Wong, Nature Methods 2011) — blue, orange,
# green, … — used for a few distinct curves (I/Q, data/fit) where a gradient would
# give hard-to-read pale endpoints.
const WONG = [colorant"#0072B2", colorant"#E69F00", colorant"#009E73",
              colorant"#CC79A7", colorant"#56B4E9", colorant"#D55E00",
              colorant"#F0E442", colorant"#000000"]

# N plotting colors. `categorical=true` (default for a small N) gives the Wong
# high-contrast set; otherwise a ColorSchemes gradient (default :haline, the one
# in your notebook) — right for many-trace sweeps.
function palette_n(n::Integer; scheme::Symbol = :haline, categorical::Bool = false)
    if categorical
        return [WONG[mod1(i, length(WONG))] for i in 1:n]
    end
    n <= 1 ? [get(colorschemes[scheme], 0.5)] :
             get(colorschemes[scheme], range(0, 1, length = n))
end

# ---------------------------------------------------------------------------
# Publication theme — Latin Modern (LaTeX) fonts, journal-column sizing.
# `size` in points; 460 ≈ a single PRL/JMR column at 72 dpi. Use set_theme!(theme_pub())
# or `with_theme(theme_pub()) do ... end`.
# ---------------------------------------------------------------------------
function theme_pub(; size = (460, 320), fontsize = 14)
    merge(theme_latexfonts(),
          Theme(; size = size, fontsize = fontsize,
                # (left, right, bottom, top): extra right/top room so the last
                # x-tick label and top y-tick label aren't clipped at the edge.
                figure_padding = (8, 16, 6, 10),
                Lines = (linewidth = 1.5,),
                Axis = (
                    xtickalign = 1, ytickalign = 1,
                    xminortickalign = 1, yminortickalign = 1,
                    xticksize = 8, yticksize = 7,
                    xminorticksize = 5, yminorticksize = 4,
                    xlabelsize = 18, ylabelsize = 18,
                    xticklabelsize = 14, yticklabelsize = 14,
                    xminorticksvisible = true, yminorticksvisible = true,
                    xminorticks = IntervalsBetween(5),
                    yminorticks = IntervalsBetween(2),
                    xgridvisible = false, ygridvisible = false,
                    xminorgridvisible = false, yminorgridvisible = false,
                )))
end

# Your `my_custom_plot`, generalized: spawn a styled Axis at a layout position.
# Anything you pass via kw (limits, xscale, title, xlabel, ylabel, …) overrides
# the theme defaults. Labels default to LaTeX so units render properly.
pub_axis(pos; kw...) = Axis(pos; kw...)

# ---------------------------------------------------------------------------
# Auto-label: take the axis labels straight from the CSV header names, so a
# field-swept file labels "Magnetic Field (G)" and a time trace "Time (ns)"
# with nothing typed. Only fills a label you haven't already set on `ax`.
#   data, names = read_atomize(path); autolabel!(ax, names)            # x=col1, y=col2
#   autolabel!(ax, names; x = 1, y = 3)                                # pick columns
# Pass `latex = true` to wrap a label as L"\text{…}" (matches your notebook style).
# ---------------------------------------------------------------------------
function autolabel!(ax, names; x::Integer = 1, y::Integer = 2, latex::Bool = false)
    wrap(s) = latex ? latexstring("\\text{" * s * "}") : s
    if 1 <= x <= length(names) && isempty(string(ax.xlabel[]))
        ax.xlabel = wrap(names[x])
    end
    if 1 <= y <= length(names) && isempty(string(ax.ylabel[]))
        ax.ylabel = wrap(names[y])
    end
    return ax
end

# ---------------------------------------------------------------------------
# Batch load: every CSV matching `pattern` in `dir`, sorted, as (name, data, cols).
# Replaces the 15 hand-written readdlm lines + the all_tr list.
#   for (fname, data, names) in load_glob("sweep_dir"); lines!(ax, data[:,1], data[:,2]); end
# ---------------------------------------------------------------------------
function load_glob(dir::AbstractString; pattern::Regex = r"\.csv$"i)
    files = sort(filter(f -> occursin(pattern, f), readdir(dir)))
    map(files) do f
        data, names = read_atomize(joinpath(dir, f))
        (name = f, data = data, names = names)
    end
end

# ---------------------------------------------------------------------------
# One-call figure from a file (or several files): read → plot → auto-label.
# By default plots column 1 (x) vs every other column (y), labels axes from the
# header, and overlays multiple files with the haline palette + filename legend.
#   fig = plot_atomize("trace.csv")
#   fig = plot_atomize(["a.csv","b.csv"]; ys = 2, phase = 0.1)   # real(iq), one y-col
#   save("fig.pdf", plot_atomize("trace.csv"; autolabel = true))
# `ys` selects y column(s); omit to use all non-x columns. `phase` (if given)
# combines cols (2,3) into real(iq) instead of plotting raw columns.
# ---------------------------------------------------------------------------
function plot_atomize(paths; x::Integer = 1, ys = nothing, phase = nothing,
                      autolabel::Bool = true, latex::Bool = false, axis = (;), kw...)
    files = paths isa AbstractString ? [paths] : collect(paths)
    multi = length(files) > 1
    # Pass 1: gather every series (xv, yv, label) so colors vary per LINE, not per
    # file — otherwise I and Q (or Data and Fit) in one file share a color.
    series = Tuple{Vector{Float64}, Vector{Float64}, String}[]
    names0 = String[]
    for (i, p) in enumerate(files)
        data, names = read_atomize(p)
        i == 1 && (names0 = names)
        fname = replace(basename(p), r"\.csv$"i => "")
        xv = Float64.(data[:, x])
        if phase !== nothing                                   # I/Q → real(phased)
            push!(series, (xv, Float64.(real(iq(data; phase = phase))), multi ? fname : ""))
        else
            cols = ys === nothing ? setdiff(1:size(data, 2), x) :
                   (ys isa Integer ? [ys] : collect(ys))
            for c in cols
                # multi-file: label by filename; single file: label by column name
                lbl = multi ? fname : (c <= length(names) ? names[c] : "col $c")
                push!(series, (xv, Float64.(data[:, c]), lbl))
            end
        end
    end
    # Pass 2: draw with a palette sized to the number of lines.
    fig = Figure()
    ax  = pub_axis(fig[1, 1]; axis...)
    # few distinct curves → high-contrast Wong set; many (a sweep) → gradient
    pal = palette_n(max(length(series), 1); categorical = length(series) <= length(WONG))
    for (k, (xv, yv, lbl)) in enumerate(series)
        lines!(ax, xv, yv; color = pal[k], label = lbl)
    end
    if autolabel
        yidx = ys === nothing ? min(2, length(names0)) :
               (ys isa Integer ? ys : first(ys))
        autolabel!(ax, names0; x = x, y = yidx, latex = latex)
    end
    length(series) > 1 && axislegend(ax; framevisible = false)
    return fig
end

end # module
