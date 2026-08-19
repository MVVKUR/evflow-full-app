# 5. Data and Modelling

## 5.1. Data Usage

Iteration 3 supports Epic 4, EV Demand Heatmap Dashboard, and Epic 5, Site Feasibility & Financial Analytics. Both epics answer questions about places rather than about individual charging stations, so the unit of analysis changes. Every dataset in this iteration is reduced to a common spatial unit: a 500 m cell on a regular grid covering the 14 kabupaten and kota of Jabodetabek, 28,176 cells in total. A dataset earns its place in the iteration only if it contributes a measurable attribute to that cell, either as a signal of where charging demand arises, as a constraint on where a station may be built, or as the existing supply against which a gap is measured.

| Dataset | Source | Licence | Contribution |
|---|---|---|---|
| Land use | OpenStreetMap, Geofabrik Java extract | ODbL 1.0 | area share by class per cell |
| Road network | OpenStreetMap, Geofabrik Java extract | ODbL 1.0 | connectivity per cell |
| Points of interest | OpenStreetMap, Geofabrik Java extract | ODbL 1.0 | activity counts per cell, 17 categories |
| Population | WorldPop 2026 constrained, 100 m, release R2025A | CC BY 4.0 | residents per cell |
| Administrative boundaries | HDX COD-AB Indonesia; geoBoundaries gbOpen | CC BY 3.0 IGO | study mask and statistical join key |
| SPKLU footprint | PLN registry, Open Charge Map, OpenStreetMap | mixed by feed | existing supply and cell label |
| Reference dataset | Maurya et al., six German cities | repository licence | method validation only |

### 5.1.1. Land Use

Land use describes what a place is for, and therefore what kind of charging demand it generates. Four classes are measured as a share of each cell's area: commercial, retail, residential, and industrial. The distinction matters operationally rather than descriptively. Commercial and retail areas produce short opportunistic charging during errands, residential areas produce long overnight sessions, and industrial estates concentrate fleet activity that a single site can serve repeatedly.

The polygons are extracted from a dated Geofabrik snapshot of the Java extract, `java-260814.osm.pbf`, captured on 14 August 2026 at 895 MB. A dated snapshot is used in preference to the rolling `-latest` file so that the extraction can be repeated and audited later. The raw protocol buffer file is parsed directly rather than Geofabrik's pre-classified shapefiles, because four of the categories required by the point-of-interest schema below are not separable in the shapefile classification.

How much of the region actually carries a land use tag varies sharply by class. The table below reports coverage over all 28,176 cells.

| Class | Cells with any value | Share of grid | Mean over all cells | Mean where present | Highest |
|---|---|---|---|---|---|
| Residential | 12,201 | 43.3% | 0.1668 | 0.3852 | 1.0000 |
| Industrial | 3,360 | 11.9% | 0.0380 | 0.3190 | 1.0000 |
| Commercial | 2,025 | 7.2% | 0.0096 | 0.1332 | 0.9684 |
| Retail | 659 | 2.3% | 0.0016 | 0.0698 | 0.6432 |

Two limits follow from this and both are carried into the modelling work.

Retail is too sparse to use as a feature on its own. It is present in 2.3% of cells and averages 0.0016 across the grid, so a model given this column would be fitting almost entirely to absence. Retail demand will instead be represented through the point of interest counts, which are denser and measure the same underlying activity. The column is kept in the table for completeness and for later snapshots, not because it is usable today.

The four shares are independent coverages rather than a partition, so they do not sum to 1. OpenStreetMap allows polygons of different classes to overlap the same ground, and 657 cells do exceed a combined share of 1.0, reaching 2.19 at the extreme. Overlapping polygons within a single class were dissolved during extraction so that no class double counts itself, but no dissolve is applied across classes because a place genuinely tagged as both residential and industrial is a fact about the source rather than an error to remove. The unmapped remainder of a cell means absent from OpenStreetMap, not empty on the ground, and coverage of 43.3% for the densest class shows how much of Jabodetabek carries no land use tag at all.

### 5.1.2. Road Network

A charging station is only useful if drivers can reach it without inconvenience, so road connectivity is treated as a first-class feature rather than as context. Three attributes are computed per cell from the drivable network of the same snapshot: intersection count, road segment count, and total road length. Connectivity ranked among the strongest predictors in the reference study reproduced in section 5.3.2, which supports treating it as a demand proxy in its own right.

The EV-FLOW backend already maintains an OSMnx drive graph for its routing engine, but that build covers core Jakarta only. For Iteration 3 the graph is rebuilt at the full Jabodetabek extent so that connectivity features are populated for Bogor, Depok, Tangerang, and Bekasi rather than returning null outside the capital.

### 5.1.3. Points of Interest

Seventeen categories of point of interest are counted per cell, assigned by centroid location. Thirteen mirror the reference study exactly (parking, parking spaces, restaurants, parks, schools, universities, cinemas, libraries, community centres, places of worship, town halls, government offices, and civic buildings), which keeps the two feature matrices comparable and allows the reference model's behaviour to be interpreted against ours.

Four categories were added for the Indonesian context: fuel stations, shopping malls, hospitals, and highway rest areas, drawn from the siting categories named in Kepmen ESDM 24.K/2025. These reflect where Indonesian drivers already stop, which is not identical to the German pattern the reference study encodes.

### 5.1.4. Population

Population per cell is derived from WorldPop's constrained estimate for Indonesia for the year 2026, taken from the Global 2015 to 2030 series, release R2025A, at 100 m resolution and approximately 170 MB. The constrained variant assigns population only to pixels where buildings are detected, rather than distributing it evenly across administrative areas. At 500 m cell size this distinction is material: an unconstrained product would place residents in rice fields and forest and inflate the apparent demand of rural cells.

The 2026 figure is a model projection, not a census count, and is described as such wherever it appears in the dashboard. To keep projected values anchored to official statistics, cell totals are calibrated so that they aggregate to the population projections published by BPS for each kabupaten and kota, retrieved through the BPS WebAPI. The earlier WorldPop constrained series ends at 2020 and was rejected on grounds of currency, since a dashboard published in 2026 should not present six-year-old population as current.

### 5.1.5. Administrative Boundaries

Two boundary products serve two different purposes. The geoBoundaries gbOpen ADM2 layer defines the study area and is the mask from which the grid was cut. The HDX Common Operational Dataset for Indonesia, a 277 MB geodatabase, supplies the same 14 kabupaten and kota together with 187 kecamatan at ADM3, each carrying a P-code. The P-code is the reason this second product is needed: removing its country prefix yields the BPS kode wilayah, which is the join key that allows official statistics to attach to map geometry. Without it, published population and commuter figures have no reliable path onto the grid.

Boundaries serve a second function that emerged during cleaning. The province and city fields in the station feeds are free text written to three different conventions, and the same administrative area arrives under several spellings, including a typographic error that reached the production database. Deriving area labels from boundary polygons by spatial containment removes that class of error entirely.

### 5.1.6. SPKLU Station Footprint

The existing charging network is assembled from three feeds: the PLN SPKLU registry with 3,029 records nationally, Open Charge Map with 527 records for the Jakarta area, and OpenStreetMap with 13 records. After normalisation and cross-source de-duplication the footprint is 2,931 stations nationally, of which 1,236 fall inside the Jabodetabek service area, carrying 3,434 physical connectors. These are the same counts served by the deployed EV-FLOW API, which ties the analysis to the production system rather than to a private copy of the data.

The footprint plays two roles. It is the supply side of the gap analysis, since a cell already served needs no new station. It is also the source of the cell-level label discussed in section 5.2.4.

### 5.1.7. Reference Dataset

The processed dataset published with the reference study contains 10,824 cells across German cities with point-of-interest, road, and population features. It is used solely to validate the methodology before committing to a port, and no conclusion about Jabodetabek is drawn from it. Its role is described in section 5.3.2.

## 5.2. Data Preparation

Preparation turns the raw downloads into one table the analysis can work with. There are four steps, and each one answers a plain question: where are we looking, what is already there, what is each place like, and which places already have a station.

### 5.2.1. Grid Construction

The first step divides Jabodetabek into squares of 500 metres by 500 metres, about the size of a residential block. The whole region becomes 28,176 squares, and every later number in this report is attached to one of them.

Squares are used because places have to be compared fairly. Comparing by kelurahan would not be fair, since a kelurahan in central Jakarta can be a fraction of the size of one in Kabupaten Bogor, so a count of shops or people would mean something different in each. A fixed square makes every place the same size, and a count means the same thing everywhere.

The squares are cut to the real administrative outline of the region rather than to a rectangle around it. Without that cut, squares of open sea in Jakarta Bay and squares of neighbouring regencies would sit in the table and compete as candidate sites. The effect is measurable: of the 1,236 stations inside the rectangle, 1,196 fall inside the real outline and 40 do not.

Distances and areas are measured in a metre-based map projection, while the results are stored in latitude and longitude to match the production database. The conversion between the two was checked against a known landmark before any measurement was taken.

### 5.2.2. Station Cleaning

The second step builds one reliable list of the stations that already exist. Three sources are available: the PLN registry, Open Charge Map, and OpenStreetMap. The difficulty is that the same station often appears in two or three of them under slightly different names and slightly different coordinates, so simply adding the lists together counts one station several times.

Cleaning runs in two passes. The first maps every source onto the same set of fields and drops records without usable coordinates. The second treats any two points within 75 metres of each other as the same station and merges them, preferring the PLN record where they disagree, and keeping a note of which sources contributed. The sequence reduces 3,569 raw records to 2,931 real stations, of which 1,236 are in Jabodetabek.

The merge is worth its cost. Of the Jabodetabek stations, 718 come from PLN alone, 355 appear in both PLN and Open Charge Map, and 150 are known only to Open Charge Map. Those 150 are mostly private operators, and using the PLN registry on its own would leave them off the map entirely.

Two problems in the source data shaped later decisions. Province and city names are typed differently by each source, and one spelling error had already reached the live database, so area names are now taken from the boundary map by position rather than trusted as text. Separately, the reference study's own published data was found to contain two columns of row numbers that the model was treating as meaningful predictors. Both were removed before the reproduction described in section 5.3.2.

### 5.2.3. Feature Engineering

The third step describes each square with numbers. A square ends up looking like a short report card: how many people live there, how many restaurants, malls, fuel stations and other places of interest sit inside it, how much of its area is shops or housing or industry, how many road junctions and how much road length it contains, how many charging stations it already has, and how far the nearest one is.

These numbers are what the later stages compare. A square with many residents, many places people stop at, good road access, and no station nearby is the shape of a strong candidate, and every part of that sentence is one of the columns above.

At the time of writing, the station and coverage columns are complete. The counts drawn from OpenStreetMap and the population figures are still being produced, with the source files downloaded and the extraction running.

### 5.2.4. Label Repair

The fourth step marks which squares already contain a station. That mark is the answer key: a model can only learn what a good location looks like if it is shown places that already have one.

An earlier version of the answer key was built from OpenStreetMap alone and found 19 squares out of 27,941, a rate below one in a thousand. Nothing can be learned from nineteen examples. Rebuilding the same key from the merged three-source list found 889 squares, a forty-six-fold increase.

The gain came from using data the project already held, not from any change of method, and it is the single step that made the supervised work in section 5.3.2 possible at all.

## 5.3. Modelling Plan

The work is planned in three stages, ordered so that each one only claims what its data can support. Stage A runs on what is already in hand. Stage B needs the usage figures described below. Stage C needs Stage B together with the planning and electrical data.

### 5.3.1. Stage A: Finding Underserved Areas

Stage A uses no machine learning. Each square is given a score by adding up its features with weights: distance from the nearest existing station, how many people live there, how busy the surroundings are, and how well connected the roads are. Squares that score highly are places with demand and without service.

The weights are controls on the dashboard rather than fixed numbers in the code. A planner who wants to give more importance to population moves that weight and sees the map change. This keeps the reasoning open to inspection, since anyone can ask why one site outranks another and be shown the arithmetic.

The high-scoring squares are then grouped into fifteen suggested points, which is the automatic recommendation Epic 4 asks for. Kepulauan Seribu is left out of the grouping, because its squares are separated by sea and would pull the suggested points into the bay.

A first version of this already runs, using distance from existing stations only, without the population and activity figures. It produced fifteen points, each at least 10.42 km from any station. It is reported here as proof that the mechanism works from end to end, not as advice about where to build: a score based only on distance favours places that are far from stations and equally far from people, which is exactly what the missing figures will correct.

### 5.3.2. Stage B: Learning From Stations That Already Exist

Before adapting the reference method, it was tested on its own data in the hardest reasonable way: train on all but one city, then predict the city the model has never seen. Averaged over the cities, the score was 0.893, against 0.905 when the data was split at random. The small difference matters, because it shows the method still works in a city it was not trained on, which is precisely the situation here.

The question the model answers changes for Jabodetabek, and the change is deliberate. A model trained to predict where stations exist would be learning where PLN has chosen to build, and the published figures show why that is a problem: of the stations recorded nationally, 1,876 belong to the PLN network, against 716 independent operators and 405 carmaker sites. PLN sites follow the location of PLN premises and government targets rather than customer demand, so a model trained on them would recommend more PLN premises.

Instead the model is trained to predict how busy a location will be. A published dataset provides transaction counts for 139 charging stations in Greater Jakarta, ranging from 8 to 1,953 with a middle value of 425, and those counts become the answer the model learns to predict.

Learning from 139 examples places real limits on the design, and the limits are stated rather than worked around. The model is given roughly eight to ten pieces of information about each place, chosen for their relevance, instead of the thirty or more available, because a model with too many inputs and too few examples memorises them. Two rules prevent the model from cheating: information about existing stations is never used to predict that a station exists, and it is used only as a measure of nearby competition when predicting how busy a place will be.

### 5.3.2.1. Choosing the Algorithm

No model has been fitted yet. The algorithm will be chosen on two grounds: the properties of the labelled data once it is examined, and a comparison with how the reference study made the same decision.

**Diagnostics to run first.** Three checks will decide which families are admissible, and they will be run before any model is fitted.

| Check | Decides |
|---|---|
| Compare the spread of the transaction counts against their average | whether ordinary count methods are usable, or a wider spread must be modelled explicitly |
| Test whether a logarithm straightens the lopsided target | whether the target should be transformed at all |
| Measure how strongly the candidate inputs agree with one another | whether plain regression is stable, or shrinkage is required |

**What the reference study did, and what will differ.** Its selection sits in `notebooks/modeling.ipynb`, code cells 8 and 9.

- It chose no algorithm. `all_estimators(type_filter='classifier')` fits every classifier in the installed library, about forty, and the best score is reported. The set therefore depends on the library version rather than on a stated decision, which is why no algorithm is named in its documentation.
- It applied no tuning. Every model is built with default settings, so the ranking partly reflects whose defaults suit the data.
- It hid failures. A bare `try/except` drops any model that errors without recording which or why.
- It chose using the held out score, which makes the reported figure optimistic.
- It also called `roc_auc_score` on predicted labels rather than probabilities. For binary labels that quantity is balanced accuracy, not area under the curve, and the published table shows the AUC and Recall columns matching to six decimal places.

This work will differ on all five points: a shortlist fixed in advance, tuning declared, failures recorded, selection by cross validation on the training data only, and metrics chosen to match the task.

**Shortlist to be considered.**

- *Floor.* Two deliberately simple predictors: always answer the middle value, and use the single strongest input alone. Anything more elaborate must beat both, or the added complexity is not earning its place.
- *Negative binomial.* Intended first choice for a count target whose spread exceeds what ordinary count methods assume, since it needs no transformation and its results read as multipliers a planner can be shown.
- *Ridge regression.* For the case where inputs agree closely with one another, shrinking them together rather than letting one swing positive and the other negative, while keeping coefficients that can be defended.
- *Elastic net.* Where inputs also need dropping. Preferred over the simpler alternative that drops inputs, which would keep one of a closely agreeing pair and discard the other arbitrarily.
- *Random forest and gradient boosting.* Comparisons only, constrained to shallow trees. A clear win indicates a pattern straight lines cannot capture; no win means the simpler model can be released knowing nothing was left behind.
- *Excluded.* Neural networks, which 139 examples cannot support.

**Selection rule.** By cross validation on the training data, never by the score on the held out set. Where models finish close together, the simplest within one standard error of the best will be preferred, since at this sample size differences are expected to fall inside ordinary variation.

**Testing protocol.** Examples separated by kabupaten or kota rather than at random, because two stations in the same area are too alike for a random split to be honest. Separation by kecamatan reported as a secondary check, noting that most kecamatan contain at most one station. Two measures reported together: average error in transactions, which reads directly, and agreement between the predicted and actual ordering, since planners act on which sites rank highest.

**Reporting rule.** Every prediction published as a range rather than a single number, because 139 examples cannot support a bare figure.

### 5.3.3. Stage C: Feasibility and Financial Figures

Stage C answers the question a planner asks about one specific point: is this worth surveying. Three things are combined. How much demand the location has, taken from Stage A or Stage B. Whether anything may legally and physically be built there, from land use rules and the spare capacity of the nearest electrical substation, which remove a location from the list rather than lowering its score. And how much competition is already nearby.

The financial part is designed but held back. Estimating a return needs real usage figures, and the usage data currently in the production database was generated by a simulation. Building a payback figure on it would produce confident numbers from invented inputs. Until real usage is available, the dashboard shows the cost side as estimates, and the income side is entered by the planner as an assumption rather than presented as a prediction. Payback is then calculated from those stated assumptions, so every number on the screen can be traced to where it came from.

### 5.3.4. Risks Carried Forward

Four risks are carried into the modelling work. Learning from 139 examples limits how confident any prediction can be, so a range is reported alongside each figure rather than a single number. The usage figures are a snapshot and will age, so retraining is planned once the product collects real usage of its own. The land use planning maps carry no stated licence, so nothing derived from them is published until that is settled with the issuing agency. Finally, simulated usage stays in the database because the driver features depend on it, so every value carries a marker showing whether it was measured or generated, and no financial figure may be calculated from a generated one.
