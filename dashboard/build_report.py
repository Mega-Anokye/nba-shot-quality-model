"""Generate the Power BI Project (PBIP) report files in PBIR format.

Run:  python dashboard/build_report.py
Then open "dashboard/NBA Shot Quality.pbip" in Power BI Desktop and click Refresh.

Pages
  1. Curry career      season slicer, KPI cards, PAE by season, PAE by zone, season table
  2. Shot chart        every Curry shot on a drawn court, filters for season, result and zone
  3. League            leaderboard with min-shots slicer, shot quality vs shot making scatter
"""

import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "NBA Shot Quality"
REPORT = HERE / f"{NAME}.Report"
MODEL = HERE / f"{NAME}.SemanticModel"
DEF = REPORT / "definition"
ART = HERE / "art"
BASE_THEME = "CY24SU10"
PBI_THEMES = None   # set at runtime from the Power BI Desktop install

S = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
SCHEMA = {
    "version": f"{S}/versionMetadata/1.0.0/schema.json",
    "report": f"{S}/report/3.0.0/schema.json",
    "pages": f"{S}/pagesMetadata/1.0.0/schema.json",
    "page": f"{S}/page/2.0.0/schema.json",
    "visual": f"{S}/visualContainer/2.0.0/schema.json",
    "pbir": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "platform": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
}

NAVY, ROYAL, GOLD, ORANGE = "#1D428A", "#2b62c4", "#FFC72C", "#eb6834"
PAGE_BG, INK, MUTED = "#f6f3ec", "#0b0b0b", "#52514e"
W, H = 1280, 720


# ---------- tiny helpers for Power BI's expression JSON ----------

def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = f"'{v}'"
    return {"expr": {"Literal": {"Value": s}}}


def colour(hex_):
    return {"solid": {"color": lit(hex_)}}


def measure(name, table="Metrics"):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def column(table, name):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def summed(table, name):
    """Column wrapped in Sum: a scatter with one dot per shot needs aggregated X and Y."""
    return {"Aggregation": {"Expression": column(table, name), "Function": 0}}


def proj(field, display=None):
    if "Aggregation" in field:
        inner = field["Aggregation"]["Expression"]["Column"]
        base = f"{inner['Expression']['SourceRef']['Entity']}.{inner['Property']}"
        p = {"field": field, "queryRef": f"Sum({base})", "nativeQueryRef": f"Sum of {inner['Property']}"}
        if display:
            p["displayName"] = display
        return p
    inner = next(iter(field.values()))
    ref = f"{inner['Expression']['SourceRef']['Entity']}.{inner['Property']}"
    p = {"field": field, "queryRef": ref, "nativeQueryRef": inner["Property"]}
    if display:
        p["displayName"] = display
    return p


def resource(item):
    return {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1,
                                             "ItemName": item}}}


def container(title=None, background=True, border=False):
    obj = {}
    if title:
        obj["title"] = [{"properties": {"show": lit(True), "text": lit(title), "fontColor": colour(NAVY),
                                        "fontSize": lit(12), "bold": lit(True)}}]
    else:
        obj["title"] = [{"properties": {"show": lit(False)}}]
    obj["background"] = [{"properties": {"show": lit(background), "color": colour("#FFFFFF"),
                                         "transparency": lit(0)}}]
    obj["border"] = [{"properties": {"show": lit(border), "color": colour(GOLD), "radius": lit(8)}}]
    obj["dropShadow"] = [{"properties": {"show": lit(background)}}]
    return obj


def visual(name, vtype, x, y, w, h, roles=None, objects=None, title=None, z=0, sort=None,
           background=True, cobjects=None):
    v = {"visualType": vtype}
    if roles:
        v["query"] = {"queryState": {r: {"projections": p} for r, p in roles.items()}}
        if sort:
            v["query"]["sortDefinition"] = {"sort": sort, "isDefaultSort": True}
    if objects:
        v["objects"] = objects
    v["visualContainerObjects"] = cobjects or container(title, background)
    v["drillFilterOtherVisuals"] = True
    return {"$schema": SCHEMA["visual"], "name": name,
            "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}, "visual": v}


# ---------- reusable pieces ----------

def banner(prefix, subtitle):
    img = visual(f"{prefix}banner", "image", 0, 0, W, 96, z=0, background=False,
                 objects={"general": [{"properties": {"imageUrl": resource("banner.png")}}],
                          "imageScaling": [{"properties": {"imageScalingType": lit("Fill")}}]},
                 cobjects=container(None, background=False))
    text = visual(f"{prefix}title", "textbox", 112, 14, 900, 70, z=1000, background=False,
                  objects={"general": [{"properties": {"paragraphs": [
                      {"textRuns": [{"value": "“Steph Curry is the greatest shooter God ever created.”",
                                     "textStyle": {"fontSize": "20pt", "fontWeight": "bold", "fontStyle": "italic",
                                                   "color": "#FFFFFF"}}]},
                      {"textRuns": [{"value": subtitle,
                                     "textStyle": {"fontSize": "11pt", "color": GOLD}}]},
                  ]}}]},
                  cobjects=container(None, background=False))
    return [img, text]


def season_slicer(name, x, y, w, h, z):
    return visual(name, "slicer", x, y, w, h, z=z, title="Season",
                  roles={"Values": [proj(column("Season", "Season"))]},
                  objects={"data": [{"properties": {"mode": lit("Basic")}}],
                           "selection": [{"properties": {"selectAllCheckboxEnabled": lit(True),
                                                         "singleSelect": lit(False)}}],
                           "header": [{"properties": {"show": lit(False)}}]})


def card(name, x, y, w, h, z, m, label):
    return visual(name, "card", x, y, w, h, z=z,
                  roles={"Values": [proj(measure(m), label)]},
                  objects={"labels": [{"properties": {"color": colour(NAVY), "fontSize": lit(26),
                                                      "labelDisplayUnits": lit(1)}}],
                           "categoryLabels": [{"properties": {"show": lit(True), "color": colour(MUTED),
                                                              "fontSize": lit(10)}}]},
                  cobjects=container(None, background=True))


# ---------- pages ----------

def page_career():
    v = banner("c_", "Extra points Steph scored compared with an average NBA shooter taking the exact same shots  ·  2009-10 to 2025-26")
    v.append(season_slicer("c_season", 16, 112, 150, 592, 10))
    cards = [("Curry PAE", "Extra points vs an average shooter"), ("Curry PAE per 100", "Extra points per 100 shots"),
             ("Curry Points per Shot", "Points Steph scored per shot"),
             ("Curry Expected per Shot", "Points an average shooter would get per shot"),
             ("Curry FG% Above Expected", "How much better he shoots than average")]
    cw = (W - 182 - 16 - 4 * 12) / 5
    for i, (m, lab) in enumerate(cards):
        v.append(card(f"c_card{i}", 182 + i * (cw + 12), 112, cw, 100, 20 + i, m, lab))
    v.append(visual("c_by_season", "clusteredColumnChart", 182, 224, 660, 268, z=30,
                    title="Extra points per 100 shots, season by season (above zero = better than average)",
                    roles={"Category": [proj(column("Season", "Season"))],
                           "Y": [proj(measure("Curry PAE per 100"), "Extra points per 100 shots")],
                           "Tooltips": [proj(measure("Curry Shots"), "Shots"), proj(measure("Curry PAE"), "Extra points")]},
                    sort=[{"field": column("Season", "Season"), "direction": "Ascending"}],
                    objects={"dataPoint": [{"properties": {"fill": colour(ROYAL)}}],
                             "labels": [{"properties": {"show": lit(False)}}],
                             "valueAxis": [{"properties": {"gridlineShow": lit(True)}}]}))
    v.append(visual("c_by_zone", "clusteredBarChart", 854, 224, 410, 268, z=31,
                    title="Where on the court he beats the average shooter",
                    roles={"Category": [proj(column("Curry Shot", "Zone"), "Spot on the court")],
                           "Y": [proj(measure("Curry PAE per 100"), "Extra points per 100 shots")],
                           "Tooltips": [proj(measure("Curry Shots"), "Shots"), proj(measure("Curry FG%"), "Steph made"),
                                        proj(measure("Curry Expected FG%"), "An average shooter would make")]},
                    sort=[{"field": measure("Curry PAE per 100"), "direction": "Descending"}],
                    objects={"dataPoint": [{"properties": {"fill": colour(ORANGE)}}],
                             "labels": [{"properties": {"show": lit(True), "color": colour(INK)}}]}))
    v.append(visual("c_table", "tableEx", 182, 504, 1082, 200, z=32, title="Season by season",
                    roles={"Values": [proj(column("Season", "Season")), proj(measure("Curry Shots"), "Shots"),
                                      proj(measure("Curry 3PA Share"), "Share that were threes"),
                                      proj(measure("Curry FG%"), "Steph made"),
                                      proj(measure("Curry Expected FG%"), "Average shooter would make"),
                                      proj(measure("Curry Points per Shot"), "His points per shot"),
                                      proj(measure("Curry Expected per Shot"), "Average shooter's points per shot"),
                                      proj(measure("Curry PAE"), "Extra points"),
                                      proj(measure("Curry PAE per 100"), "Extra per 100 shots")]},
                    sort=[{"field": column("Season", "Season"), "direction": "Ascending"}],
                    objects={"columnHeaders": [{"properties": {"backColor": colour(NAVY), "fontColor": colour("#FFFFFF"),
                                                               "bold": lit(True)}}],
                             "values": [{"properties": {"backColorSecondary": colour("#f3f6fc")}}]}))
    return "career", "Curry career", v


def page_shots():
    v = banner("s_", "Every shot Steph took. Pick a season, makes or misses, or a spot on the court; hover a dot for details.")
    v.append(season_slicer("s_season", 16, 112, 150, 380, 10))
    v.append(visual("s_result", "slicer", 16, 504, 150, 96, z=11, title="Made or missed",
                    roles={"Values": [proj(column("Curry Shot", "Result"))]},
                    objects={"data": [{"properties": {"mode": lit("Basic")}}],
                             "header": [{"properties": {"show": lit(False)}}]}))
    v.append(visual("s_zone", "slicer", 16, 612, 150, 92, z=12, title="Spot on the court",
                    roles={"Values": [proj(column("Curry Shot", "Zone"))]},
                    objects={"data": [{"properties": {"mode": lit("Dropdown")}}],
                             "header": [{"properties": {"show": lit(False)}}]}))
    # Court: 500 x 470 units, keep the plot area close to that ratio
    v.append(visual("s_court", "scatterChart", 182, 112, 640, 592, z=20, title=None,
                    roles={"Category": [proj(column("Curry Shot", "Shot ID"))],
                           "X": [proj(summed("Curry Shot", "Court X"), "Court X")],
                           "Y": [proj(summed("Curry Shot", "Court Y"), "Court Y")],
                           "Series": [proj(column("Curry Shot", "Result"))],
                           "Tooltips": [proj(column("Curry Shot", "Game Date"), "Game date"),
                                        proj(column("Curry Shot", "Distance (ft)"), "Feet from the basket"),
                                        proj(column("Curry Shot", "Zone"), "Spot on the court"),
                                        proj(column("Curry Shot", "Make Probability"), "An average shooter makes this")]},
                    objects={
                        "categoryAxis": [{"properties": {"show": lit(False), "start": lit(-250), "end": lit(250),
                                                         "gridlineShow": lit(False)}}],
                        "valueAxis": [{"properties": {"show": lit(False), "start": lit(-47.5), "end": lit(422.5),
                                                      "gridlineShow": lit(False)}}],
                        "plotArea": [{"properties": {"transparency": lit(0), "image": {"image": {
                            "name": lit("court.png"), "url": resource("court.png"), "scaling": lit("Fill")}}}}],
                        "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}],
                        "dataPoint": [{"properties": {"fill": colour(ROYAL)},
                                       "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0,
                                           "Left": column("Curry Shot", "Result"), "Right": {"Literal": {"Value": "'Made'"}}}}}]}},
                                      {"properties": {"fill": colour(ORANGE)},
                                       "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0,
                                           "Left": column("Curry Shot", "Result"), "Right": {"Literal": {"Value": "'Missed'"}}}}}]}}],
                        "markerShape": [{"properties": {"markerSize": lit(1)}}],
                    },
                    cobjects=container(None, background=True)))
    side = [("Curry Shots", "Shots taken"), ("Curry FG%", "Steph made"),
            ("Curry Expected FG%", "An average shooter would make"),
            ("Curry PAE", "Extra points vs an average shooter")]
    for i, (m, lab) in enumerate(side):
        v.append(card(f"s_card{i}", 838, 112 + i * 112, 426, 100, 30 + i, m, lab))
    v.append(visual("s_note", "textbox", 838, 560, 426, 144, z=40,
                    objects={"general": [{"properties": {"paragraphs": [
                        {"textRuns": [{"value": "How to read this", "textStyle": {"fontWeight": "bold", "color": NAVY}}]},
                        {"textRuns": [{"value": "A computer program learned how often an average NBA player makes a "
                                                "shot from each spot. It never got to peek at the season it was "
                                                "judging. Extra points = what Steph scored minus what an average "
                                                "shooter would have scored from the same shots. Power BI shows up to "
                                                "10,000 dots at once, so pick a few seasons to see every shot.",
                                       "textStyle": {"color": MUTED}}]}]}}]}))
    return "shots", "Shot chart", v


def page_league():
    v = banner("l_", "The whole NBA since 2009-10: who scores the most extra points from their shots?")
    v.append(season_slicer("l_season", 16, 112, 150, 440, 10))
    v.append(visual("l_minshots", "slicer", 16, 564, 150, 140, z=11, title="Only players with at least … shots",
                    roles={"Values": [proj(column("Min Shots", "Value"), "Shots")]},
                    objects={"data": [{"properties": {"mode": lit("Dropdown")}}],
                             "selection": [{"properties": {"singleSelect": lit(True)}}],
                             "header": [{"properties": {"show": lit(False)}}]}))
    v.append(visual("l_table", "tableEx", 182, 112, 700, 592, z=20, title="Leaderboard: extra points vs an average shooter",
                    roles={"Values": [proj(column("Player", "Player")), proj(measure("Shots")),
                                      proj(measure("Points per Shot"), "His points per shot"),
                                      proj(measure("Expected per Shot"), "Average shooter's"),
                                      proj(measure("Ranked PAE"), "Extra points"),
                                      proj(measure("PAE per 100"), "Extra per 100"),
                                      proj(measure("PAE Rank"), "Rank")]},
                    sort=[{"field": measure("Ranked PAE"), "direction": "Descending"}],
                    objects={"columnHeaders": [{"properties": {"backColor": colour(NAVY), "fontColor": colour("#FFFFFF"),
                                                               "bold": lit(True)}}],
                             "values": [{"properties": {"backColorSecondary": colour("#f3f6fc")}}]}))
    v.append(visual("l_scatter", "scatterChart", 894, 112, 370, 592, z=21,
                    title="Hard shots (left) vs points scored (up). Hover for names",
                    roles={"Category": [proj(column("Player", "Player"))],
                           "X": [proj(measure("Ranked Expected per Shot"), "Average shooter's points per shot")],
                           "Y": [proj(measure("Ranked Points per Shot"), "His points per shot")],
                           "Size": [proj(measure("Shots"))],
                           "Tooltips": [proj(measure("Ranked PAE"), "Extra points"),
                                        proj(measure("Rank Label"), "Rank")]},
                    objects={"dataPoint": [{"properties": {"fill": colour(ROYAL)}}],
                             "categoryLabels": [{"properties": {"show": lit(False)}}]}))
    return "league", "League leaderboard", v


# ---------- writing files ----------

def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


def theme():
    return {
        "name": "Warriors Court",
        "dataColors": [ROYAL, ORANGE, "#1baf7a", "#c98500", "#d55181", "#6250d6", "#008300", "#e34948"],
        "background": "#FFFFFF", "foreground": INK, "tableAccent": NAVY,
        "textClasses": {"title": {"color": NAVY, "fontFace": "Segoe UI Semibold"},
                        "label": {"color": MUTED}},
        "visualStyles": {"page": {"*": {"background": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}]}}},
    }


def main() -> None:
    import subprocess
    # Files are overwritten in place (OneDrive and Power BI can lock folders, so no folder deletes).
    # Close Power BI Desktop before running this.
    res = REPORT / "StaticResources"

    # Base theme from the local Power BI Desktop install
    loc = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop).InstallLocation"],
                         capture_output=True, text=True).stdout.strip()
    src_theme = Path(loc) / "bin/WebView2Resources/minerva/sharedresources/BaseThemes" / f"{BASE_THEME}.json"
    (res / "SharedResources/BaseThemes").mkdir(parents=True, exist_ok=True)
    shutil.copy(src_theme, res / f"SharedResources/BaseThemes/{BASE_THEME}.json")
    reg = res / "RegisteredResources"
    reg.mkdir(parents=True, exist_ok=True)
    for f in ("court.png", "banner.png", "ball.png"):
        shutil.copy(ART / f, reg / f)
    write(reg / "WarriorsCourt.json", theme())

    version_at_import = {"visual": "1.8.0", "report": "2.0.0", "page": "1.3.0"}
    write(DEF / "version.json", {"$schema": SCHEMA["version"], "version": "2.0.0"})
    write(DEF / "report.json", {
        "$schema": SCHEMA["report"],
        "themeCollection": {
            "baseTheme": {"name": BASE_THEME, "reportVersionAtImport": version_at_import, "type": "SharedResources"},
            "customTheme": {"name": "WarriorsCourt.json", "reportVersionAtImport": version_at_import,
                            "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "WarriorsCourt.json", "path": "WarriorsCourt.json", "type": "CustomTheme"},
                       {"name": "court.png", "path": "court.png", "type": "Image"},
                       {"name": "banner.png", "path": "banner.png", "type": "Image"},
                       {"name": "ball.png", "path": "ball.png", "type": "Image"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "useEnhancedTooltips": True},
    })

    pages = [page_career(), page_shots(), page_league()]
    write(DEF / "pages/pages.json", {"$schema": SCHEMA["pages"], "pageOrder": [p[0] for p in pages],
                                     "activePageName": pages[0][0]})
    for name, display, visuals in pages:
        write(DEF / f"pages/{name}/page.json", {"$schema": SCHEMA["page"], "name": name, "displayName": display,
                                                "displayOption": "FitToPage", "width": W, "height": H})
        for vis in visuals:
            write(DEF / f"pages/{name}/visuals/{vis['name']}/visual.json", vis)

    write(REPORT / "definition.pbir", {"$schema": SCHEMA["pbir"], "version": "4.0",
                                       "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write(MODEL / "definition.pbism", {"version": "4.2", "settings": {}})
    for folder, kind in [(REPORT, "Report"), (MODEL, "SemanticModel")]:
        p = folder / ".platform"
        if not p.exists():
            write(p, {"$schema": SCHEMA["platform"], "metadata": {"type": kind, "displayName": NAME},
                      "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}})
    write(HERE / f"{NAME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                  "settings": {"enableAutoRecovery": True}})
    # Warn about visual folders no longer produced by this script (delete them by hand if any)
    expected = {(name, vis["name"]) for name, _, visuals in pages for vis in visuals}
    for vdir in DEF.glob("pages/*/visuals/*"):
        if (vdir.parent.parent.name, vdir.name) not in expected:
            print(f"Stale visual folder (not regenerated): {vdir}")
    n = sum(len(p[2]) for p in pages)
    print(f"Wrote {len(pages)} pages, {n} visuals to {REPORT}")


if __name__ == "__main__":
    main()
