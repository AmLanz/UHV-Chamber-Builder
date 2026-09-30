"""Lossless JSON and portable table/geometry bundles."""
from copy import deepcopy
from pathlib import Path
import csv
import io
import json
import re
import zipfile
from . import core


def csv_table(rows):
    fields=[]
    for row in rows:
        for key in row:
            if key not in fields:fields.append(key)
    stream=io.StringIO(newline="");writer=csv.DictWriter(stream,fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key:json.dumps(v,ensure_ascii=False,separators=(",",":")) if isinstance(v,(dict,list)) else v for key,v in row.items()})
    return stream.getvalue()


def report(recipe):
    checked=core.validate(recipe);r=checked["recipe"]
    def esc(x):return str(x).replace("|","\\|").replace("\n"," ")
    lines=["# "+esc(r["name"]),"","UHV Chamber Builder "+core.VERSION+" · draft recipe · mm / degrees","",
           "Reference/visualization geometry. Fasteners, rotatable inserts and seal profiles may be schematic.","",
           "Catalog: "+r["catalog_revision"],"","## Points","","| Name | X | Y | Z |","| --- | ---: | ---: | ---: |"]
    for p in r["points"]:lines.append("| "+" | ".join(esc(p[k]) for k in ("name","x","y","z"))+" |")
    lines += ["","## Body shapes","","| Name | Shape | Reference | Enabled |","| --- | --- | --- | --- |"]
    labels={p["id"]:p["name"] for p in r["points"]}
    for b in r["bodies"]:lines.append("| "+" | ".join(map(esc,(b["name"],b["kind"],labels.get(b.get("point"),"MISSING"),b.get("enabled",True))))+" |")
    convention="Azimuth from X / elevation around X (negative azimuth selects opposite Y half)"
    lines += ["","## Flanges","","Angle convention: "+convention+". Tube-end flanges follow their parent tube.","","| Number | Name | Preset | Configuration | Face centre (mm) | Outward normal | OD | Thickness | PCD | Holes | Bore | Tube OD × wall |","| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |"]
    for f in r["ports"]:
        x=checked["resolved"].get(f["id"])
        if not x:continue
        d=x["dims"];t=x["tube"]
        fmt=lambda a:", ".join("%.6g"%v for v in a)
        values=(f.get("number",""),f["name"],f["preset"],f["configuration"],fmt(x["face"]),fmt(x["n"]),d["od"],d["thickness"],d["pcd"],str(d["bolts"])+" × "+str(d["hole"]),x["bore"],str(t["od"])+" × "+str(t["wall"]))
        lines.append("| "+" | ".join(map(esc,values))+" |")
    lines += ["","## Validation","",*("- "+esc(e["message"]) for e in checked["errors"])]
    if not checked["errors"]:lines.append("Input checks passed. This is not a native Fusion interference or structural verification.")
    lines += ["","The accompanying JSON contains the complete dimensions, overrides and defaults.",""]
    return "\n".join(lines)


def export_bundle(recipe,path):
    r=deepcopy(recipe);assets=[]
    for b in r["bodies"]:
        for key in ("asset","cavity_asset"):
            if b.get(key):
                source=Path(b[key])
                if not source.is_file():raise core.RecipeError("Missing imported body asset: "+b["name"])
                name="assets/"+re.sub(r"[^A-Za-z0-9_-]","_",b["id"])+"_"+key+".smt"
                assets.append((source,name));b[key]=name
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("recipe.json",json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False))
        for key in ("points","bodies","ports"):z.writestr(("flanges" if key=="ports" else key)+".csv",csv_table(r[key]))
        z.writestr("defaults.json",json.dumps(r["defaults"],indent=2,allow_nan=False))
        z.writestr("report.md",report(recipe))
        for source,name in assets:z.write(source,name)


def import_recipe(path,asset_directory):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:raise core.RecipeError("Recipe package exceeds 64 MB.")
    if path.suffix.lower()!=".zip":
        return core.normalize(json.loads(path.read_text(encoding="utf-8-sig")))
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>128*1024*1024:raise core.RecipeError("Expanded recipe exceeds 128 MB.")
        r=core.normalize(json.loads(z.read("recipe.json")))
        folder=Path(asset_directory)/core.uid("import");folder.mkdir(parents=True,exist_ok=True)
        for b in r["bodies"]:
            for key in ("asset","cavity_asset"):
                if not b.get(key):continue
                name=b[key]
                if not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.smt",name):raise core.RecipeError("Invalid geometry asset path.")
                target=folder/Path(name).name;target.write_bytes(z.read(name));b[key]=str(target)
                b.pop("token" if key=="asset" else "cavity_token",None)
        return r
