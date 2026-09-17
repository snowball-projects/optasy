# Team imagery

Reviewed September 13, 2026. This decision is separate from the nflverse data
review in [DATA_SOURCES.md](DATA_SOURCES.md).

## Shipped assets

Twelve of the dashboard's team logos are public-domain SVGs from Wikimedia Commons.
Each file's own description page was reviewed for its public-domain basis;
Commons API metadata also reported `Public domain` and `Copyrighted: False` at
collection. The decision does not extend to other images on Commons or to the
official NFL image URLs cited by some Commons descriptions.

| Team                  | File and source                                                                   | Commons copyright basis          |
| --------------------- | --------------------------------------------------------------------------------- | -------------------------------- |
| Cincinnati Bengals    | [CIN.svg](https://commons.wikimedia.org/wiki/File:Cincinnati_Bengals_logo.svg)    | PD-textlogo                      |
| Dallas Cowboys        | [DAL.svg](https://commons.wikimedia.org/wiki/File:Dallas_Cowboys.svg)             | PD-shape                         |
| Green Bay Packers     | [GB.svg](https://commons.wikimedia.org/wiki/File:Green_Bay_Packers_logo.svg)      | PD-textlogo                      |
| Indianapolis Colts    | [IND.svg](https://commons.wikimedia.org/wiki/File:Indianapolis_Colts_logo.svg)    | PD-ineligible                    |
| Kansas City Chiefs    | [KC.svg](https://commons.wikimedia.org/wiki/File:Kansas_City_Chiefs_logo.svg)     | PD-US-no notice                  |
| Los Angeles Chargers  | [LAC.svg](https://commons.wikimedia.org/wiki/File:Los_Angeles_Chargers_logo.svg)  | PD-textlogo                      |
| New Orleans Saints    | [NO.svg](https://commons.wikimedia.org/wiki/File:New_Orleans_Saints_logo.svg)     | PD-textlogo                      |
| New York Giants       | [NYG.svg](https://commons.wikimedia.org/wiki/File:New_York_Giants_logo.svg)       | PD-textlogo                      |
| New York Jets         | [NYJ.svg](https://commons.wikimedia.org/wiki/File:New_York_Jets_2024.svg)         | PD-textlogo; current 2024 design |
| Pittsburgh Steelers   | [PIT.svg](https://commons.wikimedia.org/wiki/File:Pittsburgh_Steelers_logo.svg)   | PD-textlogo and PD-US-no notice  |
| San Francisco 49ers   | [SF.svg](https://commons.wikimedia.org/wiki/File:San_Francisco_49ers_logo.svg)    | PD-textlogo                      |
| Washington Commanders | [WAS.svg](https://commons.wikimedia.org/wiki/File:Washington_Commanders_logo.svg) | PD-textlogo                      |

`PD-textlogo`, `PD-shape` and `PD-ineligible` are Commons determinations that the
art lacks copyrightable originality. `PD-US-no notice` concerns historical US
publication without a copyright notice; it is a US-specific basis, and the
Kansas City description explicitly notes that protection may differ elsewhere.
These are documented source determinations, not a blanket license from the NFL.

Team marks retain their trademark status. sideline displays them beside team names
solely to identify the teams in the report, without implying sponsorship or
endorsement. They are not snowball branding and do not inherit the software's
MIT license. Retain these source links when reusing the asset collection.

## Complete team identification

The September 13 follow-up explicitly requests proper logos for all teams.
The remaining twenty teams now use small PNG thumbnails sourced from each
team's current English Wikipedia file page. These are copyrighted logos, not
public-domain works or CC BY assets. Their exact file pages, copyright notices,
download URLs, dimensions and checksums are recorded in `web/team-assets.json`.
The source pages identify their own uses as non-free; Wikipedia's rationale is
not a license for sideline and is not presented as one.

sideline's use is limited to editorial team identification in factual roster,
matchup and injury reporting. The complete symbol is needed for identification,
but only a small thumbnail is retained and it is displayed at up to 64 CSS
pixels. It is not a branding asset, merchandise design, downloadable logo
library or claim of affiliation. This contextual, noncommercial use does not
replace a high-resolution logo asset or an official service. The creative
nature and use of the complete marks remain relevant limits. This is a
use-specific rationale under the [US fair-use factors](https://www.copyright.gov/fair-use/),
not an affirmative NFL license or a guarantee that all jurisdictions treat the
use identically. Downstream uses require their own assessment; do not label
these images MIT, CC BY or unrestricted.

All 32 teams have a current identifying mark. The Chicago asset is its primary
bear head and the Tennessee asset is the current 2026 logo. Plain team letters
remain only as a runtime fallback if an image cannot be loaded. Additional or
replacement media require a source and use review; player portraits remain
outside this decision.

## Storage and verification

[web/team-assets.json](../web/team-assets.json) is the explicit public allowlist.
It records each local path, description and license links, reviewed description
revision, original download URL, original and shipped SHA-256 digests, review
date and transformation. The twelve original SVGs were downloaded from `upload.wikimedia.org`
after their file-page review. Those SVGs total about 36 KB after sanitization. The other twenty assets are
unmodified, small PNG thumbnails (about 423 KB total), not copied source SVGs.

The downloaded SVGs were parsed as XML and restricted to static SVG drawing
elements and attributes. Non-rendering metadata/editor attributes and external
document types were removed. Executable elements, event handlers, embedded
images, external references and external CSS imports are not allowed. Geometry,
color and proportions are preserved. Local copies are committed and served by
the existing static deployment; there are no visitor requests to media providers,
image API keys, recurring media collection or service charges.

To replace an asset, recheck its exact source file and current team identity,
download the permitted original, repeat the static SVG checks, update the
manifest's provenance, use basis and hashes, and inspect its rendered appearance before
publication. Do not expand the build allowlist to arbitrary downloaded files.

## Player portraits and other sources

Player portraits are omitted. No practical, complete, zero-cost public reuse
grant was established for the source roster's player-photo URLs. The
[NFL terms](https://www.nfl.com/legal/terms/) do not establish that grant.
[Disney's terms applying to ESPN](https://disneytermsofuse.com/english/)
also do not supply an unrestricted media redistribution permission.

[nflplotR's terms](https://nflplotr.nflverse.com/) distinguish its MIT R code
from NFL content governed by its owners' terms. A library capable of rendering
logos or portraits does not establish an image license.

Individually licensed player photographs do exist, such as
[Jeffrey Beall's 2017 Patrick Mahomes photograph](https://commons.wikimedia.org/wiki/File:Patrick_Mahomes_II.JPG)
under CC BY 4.0. A photo's individual grant cannot be generalized to other
players or images. Maintaining a partial historic portrait collection would
require separate identity, attribution, crop and image-vintage review. The
dashboard therefore leaves that space for player identity and injury data.
