#!/usr/bin/env julia
# render.jl — turn Atomize CSV export(s) into a publication figure file.
#
#   julia render.jl <output.(pdf|svg|png)> <input.csv> [input2.csv ...]
#
# Output extension picks the format (PDF/SVG = vector, print-ready). Axis labels
# are read from the Atomize "#"-comment header (auto-label). This is the script
# the Data Treatment "Makie figure…" button invokes via QProcess, but it also
# works on its own from a shell. Needs CairoMakie/ColorSchemes/Colors/LaTeXStrings
# in the active Julia environment:
#   julia -e 'using Pkg; Pkg.add(["CairoMakie","ColorSchemes","Colors","LaTeXStrings"])'

# Use this folder's own Julia environment (Project.toml) so deps are pinned and
# the global env is left untouched. First run resolves + precompiles (slow once).
using Pkg
Pkg.activate(@__DIR__; io = devnull)
isfile(joinpath(@__DIR__, "Manifest.toml")) || Pkg.instantiate(; io = devnull)

include(joinpath(@__DIR__, "atomize_makie.jl"))
using .AtomizeMakie
using CairoMakie

function main(args)
    if length(args) < 2
        println(stderr, "usage: julia render.jl <output> <input.csv> [more.csv ...]")
        return 2
    end
    out, inputs = args[1], args[2:end]
    set_theme!(theme_pub())
    fig = plot_atomize(inputs; autolabel = true)
    save(out, fig)
    println("wrote ", out)
    return 0
end

exit(main(ARGS))
