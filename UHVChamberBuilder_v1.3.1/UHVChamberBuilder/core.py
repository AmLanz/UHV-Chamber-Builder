"""Fusion-independent recipe validation, coordinates and connection planning.

All lengths are millimetres and all public angles are degrees. No adsk imports.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import uuid

VERSION = "1.3.1"
SCHEMA = 1
EPS = 1e-5
CATALOG = json.loads((Path(__file__).parent / "data" / "catalog.json").read_text(encoding="utf-8"))
FLANGE_KEYS = ("od", "thickness", "pcd", "bolts", "hole", "knife", "recess", "gasket_od", "gasket_id", "gasket_t")


class RecipeError(ValueError):
    def __init__(self, message, row_id=""):
        super().__init__(message)
        self.row_id = row_id


def uid(prefix="row"):
    return prefix + "_" + uuid.uuid4().hex[:16]


def number(value, name="value", positive=False):
    if isinstance(value, bool):
        raise RecipeError(name + " must be a number.")
    try:
        x = float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        raise RecipeError(name + " must be a finite number.")
    if not math.isfinite(x) or abs(x) > 1e7:
        raise RecipeError(name + " must be finite and within ±10,000,000.")
    if positive and x <= EPS:
        raise RecipeError(name + " must be positive.")
    return x


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def scale(a, t): return tuple(x * t for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def unit(a):
    d = norm(a)
    if d < EPS: raise RecipeError("Direction points must be different.")
    return scale(a, 1/d)


def frame(azimuth=0, elevation=0, roll=0):
    """Azimuth tilts from +X; elevation sweeps the full frame around +X.

    Negative azimuth chooses the opposite Y half while preserving positive
    elevation toward +Z on both halves. Roll rotates within the face plane.
    """
    a=number(azimuth,"Azimuth");e=number(elevation,"Elevation")
    if not -180<=a<=180:raise RecipeError("Azimuth must be between −180° and +180°.")
    theta,phi,rr=map(math.radians,(abs(a),e if a>=0 else 180-e,number(roll)))
    st,ct=math.sin(theta),math.cos(theta);sp,cp=math.sin(phi),math.cos(phi)
    n=(ct,st*cp,st*sp)
    u0=(-st,ct*cp,ct*sp);v0=(0,-sp,cp)
    u=add(scale(u0,math.cos(rr)),scale(v0,math.sin(rr)))
    return u,cross(n,u),n


def angles_from_normal(n):
    """A canonical positive-azimuth representation of an outward axis."""
    return math.degrees(math.acos(max(-1,min(1,n[0])))),math.degrees(math.atan2(n[2],n[1]))


def default_settings():
    preferred = {}
    for name, tube in CATALOG["tubes"].items(): preferred.setdefault(tube["flange"], name)
    return dict(flanges=deepcopy(CATALOG["flanges"]), tubes=deepcopy(CATALOG["tubes"]),
                preferred_tubes=preferred, theme="light", show_points=True, show_axes=True,
                gasket_features=False, fasteners=False, tool_clearance=False,
                proximity_check=False, gap=10.0, seal_depth=1.3, tip_depth=0.6,
                gasket_standoff=2.0, tool_diameter=22.0, tool_length=60.0,
                bolt_length=40.0, fastener_diameter=0.0)


def new_point(name="A", xyz=(0, 0, 0)):
    return dict(id=uid("p"), name=name, x=xyz[0], y=xyz[1], z=xyz[2], visible=True)


def new_body(point, kind="sphere"):
    return dict(id=uid("b"), name=kind.title(), kind=kind, point=point, enabled=True,
                azimuth=0, elevation=0, roll=0, basis="id", diameter=200, wall=3,
                s_min=-100, s_max=100, end_minus="open", end_plus="open",
                cap_minus=3, cap_plus=3, flange_minus="DN200CF", flange_plus="DN200CF",
                x_min=-100, x_max=100, y_min=-75, y_max=75, z_min=-75, z_max=75,
                token="", source_name="", cavity_token="")


def new_port(point):
    return dict(id=uid("f"), name="Port", number="", point=point, enabled=True, azimuth=0,
                elevation=0, roll=0, distance=160, preset="DN40CF", configuration="straddled",
                overrides={}, deviate=False, tube="default", tube_basis="od", tube_diameter=38,
                tube_wall=1.5, target="auto", neck_mode="auto", neck_length=70, bore=None)


def new_recipe():
    p = new_point()
    return dict(schema=SCHEMA, version=VERSION, id=uid("chamber"), name="UHV chamber",
                units="mm", catalog_revision=CATALOG["revision"], points=[p],
                bodies=[], ports=[], defaults=default_settings())


def example_recipe():
    r = new_recipe(); p = r["points"][0]["id"]
    r["name"] = "Example spherical chamber"
    r["bodies"] = [new_body(p)]
    for name, az, el, size, dist in [("Pump",0,0,"DN100CF",190), ("Viewport",90,0,"DN40CF",160),
                                    ("Top port",90,90,"DN40CF",160)]:
        f = new_port(p); f.update(name=name, azimuth=az, elevation=el, preset=size, distance=dist)
        f["number"]=str(len(r["ports"])+1)
        r["ports"].append(f)
    return r


def normalize(raw):
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise RecipeError("Unsupported recipe schema. Import a UHV Chamber Builder schema-1 JSON file.")
    if raw.get("units") != "mm": raise RecipeError("This recipe must declare units='mm'.")
    r = deepcopy(raw)
    if not isinstance(r.get("id"), str) or not r["id"]: raise RecipeError("Recipe ID is missing.")
    r.setdefault("name","UHV chamber");r.setdefault("version",VERSION);r.setdefault("catalog_revision",CATALOG["revision"])
    if not isinstance(r.get("defaults", {}), dict): raise RecipeError("Defaults must be an object.")
    d = default_settings(); d.update(r.get("defaults", {})); d.pop("flange_angle_mode",None); r["defaults"] = d
    for key in ("flanges", "tubes", "preferred_tubes"):
        if not isinstance(d[key], dict): raise RecipeError(key + " defaults must be an object.")
    for key in ("points", "bodies", "ports"):
        if not isinstance(r.get(key), list) or len(r[key]) > 300:
            raise RecipeError(key + " must be a list of at most 300 rows.")
    seen = set()
    for row in r["points"] + r["bodies"] + r["ports"]:
        if not isinstance(row, dict): raise RecipeError("Each table row must be an object.")
        ident = row.get("id")
        if not isinstance(ident, str) or not ident or ident in seen: raise RecipeError("Missing or duplicate row ID.")
        seen.add(ident)
        if row.get("preset") == "DN150CF": row["preset"] = "DN160CF"
    # End flanges are ordinary port records with stable IDs and derived placement.
    wanted = set()
    for body in r["bodies"]:
        if body.get("kind") != "tube": continue
        for end in ("minus", "plus"):
            if body.get("end_" + end) != "flange": continue
            ident = body["id"] + "_" + end
            wanted.add(ident)
            f = next((f for f in r["ports"] if f["id"] == ident), None)
            if f is None:
                f = new_port(body.get("point")); f["id"] = ident; r["ports"].append(f)
            axis=frame(body.get("azimuth",0),body.get("elevation",0))[2]
            if end=="minus":axis=scale(axis,-1)
            az,el=angles_from_normal(axis)
            f.update(endpoint=dict(body=body["id"], end=end), point=body.get("point"), name=body.get("name", "Tube")+" / "+end,
                     preset=body.get("flange_"+end, "DN200CF"), enabled=body.get("enabled", True),
                     azimuth=az,elevation=el)
    r["ports"] = [f for f in r["ports"] if not f.get("endpoint") or f["id"] in wanted]
    for f in r["ports"]:f.setdefault("number", "")
    return r


def flange_number(value):
    """A documentation identifier, independent of row order and internal IDs."""
    text=str(value).strip() if value is not None else ""
    if not text:return None
    if not text.isascii() or not text.isdigit() or int(text)<1:
        raise RecipeError("Flange number must be a positive whole number.")
    return int(text)


def number_errors(recipe, required=False):
    errors=[];seen={}
    for f in recipe["ports"]:
        try:
            n=flange_number(f.get("number"))
            if n is None:
                if required and f.get("enabled",True):errors.append(dict(row=f["id"],message="Enter a flange number before building. Gaps are allowed."))
                continue
            if n in seen:
                message="Flange number "+str(n)+" is used more than once."
                errors.extend([dict(row=seen[n],message=message),dict(row=f["id"],message=message)])
            seen[n]=f["id"]
        except RecipeError as exc:errors.append(dict(row=f["id"],message=str(exc)))
    return errors


def require_flange_numbers(recipe):
    errors=number_errors(recipe,required=True)
    if errors:raise RecipeError(errors[0]["message"],errors[0]["row"])


def gasket_limits(dimensions,defaults):
    """Axial limits from the flange mating plane, along its outward normal."""
    outer=number(defaults["gasket_standoff"],"Gasket outer-face offset")
    return outer-dimensions["gasket_t"],outer


def flange_values(recipe, port):
    preset = port.get("preset", "DN40CF")
    if preset == "DN150CF": preset = "DN160CF"
    if preset == "Custom": base = {}
    else:
        base = deepcopy(recipe["defaults"]["flanges"].get(preset, {}))
        if not base: raise RecipeError("Unknown flange preset: " + preset, port["id"])
    if port.get("deviate") or preset == "Custom": base.update(port.get("overrides", {}))
    result = {key:number(base.get(key), key, positive=True) for key in FLANGE_KEYS}
    n = result["bolts"]
    if n != int(n) or not 3 <= n <= 100: raise RecipeError("Bolt count must be an integer from 3 to 100.", port["id"])
    result["bolts"] = int(n)
    if result["pcd"] + result["hole"] >= result["od"]:
        raise RecipeError("Bolt holes extend beyond the flange OD.", port["id"])
    if result["gasket_id"] >= result["gasket_od"]: raise RecipeError("Gasket ID must be smaller than OD.", port["id"])
    return result


def tube_values(recipe, port):
    name = port.get("tube", "default")
    if name == "default": name = recipe["defaults"]["preferred_tubes"].get(port.get("preset"), "Custom")
    if name == "Custom":
        t = number(port.get("tube_wall"), "Tube wall", True)
        d = number(port.get("tube_diameter"), "Tube diameter", True)
        od = d + 2*t if port.get("tube_basis") == "id" else d
    else:
        values = recipe["defaults"]["tubes"].get(name)
        if not values: raise RecipeError("Tube preset is missing: " + str(name), port["id"])
        od = number(values["od"], "Tube OD", True); t = number(values["wall"], "Tube wall", True)
    if od <= 2*t: raise RecipeError("Tube wall leaves no bore.", port["id"])
    return dict(od=od, wall=t, id=od-2*t, preset=name)


def lookup_point(recipe, identifier):
    row = next((p for p in recipe["points"] if p["id"] == identifier), None)
    if row is None: raise RecipeError("Reference point is missing; choose an existing point.")
    return tuple(number(row.get(k), "Point "+k.upper()) for k in ("x","y","z"))


def sphere(c, r): return dict(kind="sphere", centre=c, radius=r)
def cylinder(c, n, lo, hi, r): return dict(kind="cylinder", centre=c, axis=n, lo=lo, hi=hi, radius=r)
def box(c, axes, lows, highs): return dict(kind="box", centre=c, axes=axes, lows=lows, highs=highs)


def primitive(recipe, row):
    kind = row.get("kind")
    if kind == "existing":
        if not row.get("token") and not row.get("asset"): raise RecipeError("Select an existing solid body.",row["id"])
        return dict(row=row, outer=None, void=None, centre=(0,0,0), axes=frame())
    c = lookup_point(recipe, row.get("point")); axes = frame(row.get("azimuth",0), row.get("elevation",0), row.get("roll",0))
    t = number(row.get("wall"), "Wall thickness", True)
    if kind in ("sphere", "tube"):
        diameter = number(row.get("diameter"), "Diameter", True)
        ri = diameter/2 if row.get("basis","id") == "id" else diameter/2-t
        if ri <= EPS: raise RecipeError("Wall thickness leaves no cavity.", row["id"])
        ro = ri+t
        if kind == "sphere": outer, void = sphere(c,ro), sphere(c,ri)
        else:
            lo, hi = (number(row.get("s_"+s), "Tube endpoint") for s in ("min","max"))
            vlo, vhi = lo,hi
            for end in ("minus","plus"):
                mode = row.get("end_"+end,"open")
                if mode not in ("open","plate","flange"): raise RecipeError("Unknown tube end type.")
                if mode == "plate":
                    cap = number(row.get("cap_"+end,t), "Cap thickness", True)
                    if end == "minus": vlo += cap
                    else: vhi -= cap
                elif mode == "flange":
                    port = next(f for f in recipe["ports"] if f["id"] == row["id"]+"_"+end)
                    thickness = flange_values(recipe,port)["thickness"]
                    if end == "minus": lo += thickness
                    else: hi -= thickness
            if hi-lo <= EPS or vhi-vlo <= EPS: raise RecipeError("Tube endpoints/caps leave no positive length.", row["id"])
            outer = cylinder(c,axes[2],lo,hi,ro)
            void = cylinder(c,axes[2],vlo-EPS*10,vhi+EPS*10,ri)
    elif kind == "box":
        lows = tuple(number(row.get(k+"_min"), k+" lower offset") for k in "xyz")
        highs = tuple(number(row.get(k+"_max"), k+" upper offset") for k in "xyz")
        if any(b-a <= EPS for a,b in zip(lows,highs)): raise RecipeError("Every box upper offset must exceed its lower offset.",row["id"])
        void = box(c,axes,lows,highs)
        outer = box(c,axes,tuple(x-t for x in lows),tuple(x+t for x in highs))
    else: raise RecipeError("Unknown body shape: "+str(kind),row["id"])
    return dict(row=row, outer=outer, void=void, centre=c, axes=axes)


def intervals_intersection(a,b):
    return [(max(x,z),min(y,w)) for x,y in a for z,w in b if max(x,z)<=min(y,w)+EPS]


def intervals_union(items):
    out=[]
    for a,b in sorted(items):
        if out and a<=out[-1][1]+EPS: out[-1]=(out[-1][0],max(out[-1][1],b))
        else: out.append((a,b))
    return out


def ray_interval(shape, origin, direction):
    """Closed intervals for an infinite ray parameter; analytic convex primitives."""
    delta = sub(origin, shape["centre"])
    interval=[(-float("inf"),float("inf"))]
    def quadratic(a,b,c):
        if abs(a)<1e-14: return interval if c<=EPS else []
        disc=b*b-4*a*c
        if disc < -EPS: return []
        root=math.sqrt(max(0,disc))
        return [((-b-root)/(2*a),(-b+root)/(2*a))]
    def slab(pos,vel,lo,hi):
        if abs(vel)<1e-12:return interval if lo-EPS<=pos<=hi+EPS else []
        a,b=(lo-pos)/vel,(hi-pos)/vel
        return [(min(a,b),max(a,b))]
    if shape["kind"]=="sphere":return quadratic(dot(direction,direction),2*dot(delta,direction),dot(delta,delta)-shape["radius"]**2)
    if shape["kind"]=="cylinder":
        axis=shape["axis"]; z=dot(delta,axis); dz=dot(direction,axis)
        q=sub(delta,scale(axis,z)); dq=sub(direction,scale(axis,dz))
        return intervals_intersection(quadratic(dot(dq,dq),2*dot(q,dq),dot(q,q)-shape["radius"]**2),slab(z,dz,shape["lo"],shape["hi"]))
    for axis,lo,hi in zip(shape["axes"],shape["lows"],shape["highs"]):
        interval=intervals_intersection(interval,slab(dot(delta,axis),dot(direction,axis),lo,hi))
    return interval


def attachment(back, n, u, v, radius, cavities, limit):
    """Find an end plane whose sampled bore disc fits in the known cavity union.

    Sampling is a conservative planning aid; actual connections are checked by
    the solid kernel. It does not certify a minimum wall at a junction.
    """
    common=[(0,limit)]
    offsets=[(0,0)]+[(radius*math.cos(i*math.tau/32),radius*math.sin(i*math.tau/32)) for i in range(32)]
    for x,y in offsets:
        start=add(back,add(scale(u,x),scale(v,y)))
        spans=intervals_union([i for _,shape in cavities for i in ray_interval(shape,start,scale(n,-1))])
        common=intervals_intersection(common,spans)
        if not common:return None
    a,b=sorted(common)[0]
    depth=max(0,a)+min(0.05,max(0,b-a)/2)
    if depth<=EPS:return None
    end=add(back,scale(n,-depth))
    parents=[ident for ident,shape in cavities if any(a-EPS<=depth<=b+EPS for a,b in ray_interval(shape,back,scale(n,-1)))]
    return end,depth,parents


def port_frame(recipe, port, primitives):
    if port.get("endpoint"):
        ref=port["endpoint"]; p=next((p for p in primitives if p["row"]["id"]==ref["body"]),None)
        if p is None:raise RecipeError("Tube endpoint parent is missing or disabled.",port["id"])
        end=ref["end"]; s=number(p["row"]["s_min" if end=="minus" else "s_max"])
        f=add(p["centre"],scale(p["axes"][2],s)); n=scale(p["axes"][2],-1 if end=="minus" else 1)
        u=p["axes"][0]; v=cross(n,u)
        rr=math.radians(number(port.get("roll",0)))
        return p["centre"], f, add(scale(u,math.cos(rr)),scale(v,math.sin(rr))), add(scale(v,math.cos(rr)),scale(u,-math.sin(rr))), n
    p=lookup_point(recipe,port.get("point"))
    if port.get("toward"):
        n=unit(sub(lookup_point(recipe,port["toward"]),p))
        az,el=angles_from_normal(n);u,v,n=frame(az,el,port.get("roll",0))
    else:
        u,v,n=frame(port.get("azimuth",0),port.get("elevation",0),port.get("roll",0))
    length=number(port.get("distance"),"Face distance")
    if length<0:raise RecipeError("Face distance cannot be negative; reverse the direction.",port["id"])
    return p,add(p,scale(n,length)),u,v,n


def validate(recipe):
    errors=[]; resolved={}
    try:r=normalize(recipe)
    except RecipeError as exc:return dict(recipe=recipe,errors=[dict(row=exc.row_id,message=str(exc))],resolved={})
    errors.extend(number_errors(r))
    for p in r["points"]:
        try:lookup_point(r,p["id"])
        except RecipeError as exc:errors.append(dict(row=p["id"],message=str(exc)))
    primitives=[]
    for b in r["bodies"]:
        if not b.get("enabled",True):continue
        try:primitives.append(primitive(r,b))
        except (RecipeError,KeyError,StopIteration) as exc:errors.append(dict(row=b["id"],message=str(exc)))
    for f in r["ports"]:
        if not f.get("enabled",True):continue
        try:
            dims=flange_values(r,f); tube=tube_values(r,f)
            if f.get("endpoint"):
                pb=next(p for p in primitives if p["row"]["id"]==f["endpoint"]["body"])
                tube=dict(od=pb["outer"]["radius"]*2,wall=number(pb["row"]["wall"]),id=pb["void"]["radius"]*2,preset="Tube endpoint")
            bore=tube["id"] if f.get("bore") in (None,"") else number(f["bore"],"Bore",True)
            if bore>=dims["pcd"]-dims["hole"]:raise RecipeError("Bore intersects the bolt holes.")
            if tube["od"]>=dims["pcd"]-dims["hole"]:raise RecipeError("Neck OD reaches the bolt holes. Choose a smaller tube or larger flange.")
            if r["defaults"].get("gasket_features") and not bore<dims["knife"]<dims["recess"]<dims["od"]:raise RecipeError("Seal diameters must satisfy bore < knife < recess < flange OD.")
            if f.get("configuration") not in ("inline","straddled","rotatable"):raise RecipeError("Select a valid flange configuration.")
            p,face,u,v,n=port_frame(r,f,primitives)
            resolved[f["id"]]=dict(dims=dims,tube=tube,bore=bore,point=p,face=face,u=u,v=v,n=n,back=add(face,scale(n,-dims["thickness"])))
        except (RecipeError,KeyError,StopIteration) as exc:errors.append(dict(row=f["id"],message=str(exc) or "Parent tube is missing, disabled or invalid."))
    d=r["defaults"]
    try:number(d["gasket_standoff"],"Gasket outer-face offset")
    except RecipeError as exc:errors.append(dict(row="",message=str(exc)))
    for key in ("seal_depth","tip_depth","tool_diameter","tool_length","bolt_length","gap","fastener_diameter"):
        try:
            if number(d[key],key)<0:raise RecipeError(key+" cannot be negative.")
        except RecipeError as exc:errors.append(dict(row="",message=str(exc)))
    if d["gasket_features"]:
        try:
            if not 0<number(d["tip_depth"])<number(d["seal_depth"]):raise RecipeError("Seal profile requires 0 < tip depth < recess depth.")
            if any(x["dims"]["thickness"]<=number(d["seal_depth"]) for x in resolved.values()):raise RecipeError("Seal recess is deeper than a flange.")
        except RecipeError as exc:errors.append(dict(row="",message=str(exc)))
    return dict(recipe=r,errors=errors,resolved=resolved,primitives=primitives)


def plan(recipe):
    checked=validate(recipe)
    if checked["errors"]:
        e=checked["errors"][0];raise RecipeError(e["message"],e["row"])
    r=checked["recipe"]; primitives=checked["primitives"]
    if not primitives:raise RecipeError("Add and enable at least one main-chamber body shape.")
    ports=[]; waiting=[]; cavities=[(p["row"]["id"],p["void"]) for p in primitives if p["void"]]
    for f in sorted((f for f in r["ports"] if f.get("enabled",True)),key=lambda x:x["id"]):
        item=dict(row=f,**checked["resolved"][f["id"]])
        if f.get("endpoint"):
            item.update(outer=None,void=None,parents=[f["endpoint"]["body"]],length=0);ports.append(item)
        elif f.get("neck_mode")=="manual":
            length=number(f.get("neck_length"),"Manual neck length",True)
            end=add(item["back"],scale(item["n"],-length))
            item.update(outer=cylinder(end,item["n"],0,length,item["tube"]["od"]/2),
                        void=cylinder(end,item["n"],0,length+0.05,item["tube"]["id"]/2),
                        parents=[],length=length)
            ports.append(item)
        else:waiting.append(item)
    cavities += [(p["row"]["id"],p["void"]) for p in ports if p["void"]]
    while waiting:
        solved=[]
        for item in waiting:
            f=item["row"]; target=f.get("target","auto")
            choices=[(ident,shape) for ident,shape in cavities if target=="auto" or ident==target]
            # P is a bound, not an assumed cavity. User can choose a longer manual extent.
            limit=max(0,dot(sub(item["back"],item["point"]),item["n"]))
            result=attachment(item["back"],item["n"],item["u"],item["v"],item["tube"]["id"]/2,choices,limit)
            if result:
                end,length,parents=result
                item.update(outer=cylinder(end,item["n"],0,length,item["tube"]["od"]/2),
                            void=cylinder(end,item["n"],0,length+0.05,item["tube"]["id"]/2),
                            parents=parents,length=length)
                solved.append(item)
        if not solved:
            names=", ".join(x["row"]["name"] for x in waiting)
            raise RecipeError("No bounded cavity connection for "+names+". Select a parent tube, move the reference point inside its cavity, or set a manual neck length. Cyclic/unconnected targets cannot be resolved.",waiting[0]["row"]["id"])
        ports+=solved
        waiting=[x for x in waiting if x not in solved]
        cavities += [(x["row"]["id"],x["void"]) for x in solved]
    return dict(recipe=r,primitives=primitives,ports=sorted(ports,key=lambda x:x["row"]["id"]),cavities=cavities)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def build_subset(draft, committed, selected):
    """Build a row and its dependency closure, keeping unrelated committed rows.

    Defaults/points are shared, so all already built geometry is regenerated
    against the current shared frame. Unbuilt unrelated ports are excluded.
    """
    draft=normalize(draft)
    if not selected:return draft
    wanted={selected}
    committed=normalize(committed) if committed else None
    old_ids={x["id"] for key in ("bodies","ports") for x in (committed or {}).get(key,[])}
    wanted |= old_ids
    # All base primitives form one chamber definition and are prerequisites.
    wanted |= {b["id"] for b in draft["bodies"]}
    parent_map={f["id"]:f.get("target") for f in draft["ports"]}
    while True:
        new={parent_map[x] for x in wanted if parent_map.get(x) not in (None,"auto")}
        if new<=wanted:break
        wanted|=new
    result=deepcopy(draft);result["ports"]=[f for f in draft["ports"] if f["id"] in wanted or f.get("endpoint")]
    try:plan(result)
    except RecipeError:
        # Resolve automatic parent dependencies from the full draft, then include
        # only the needed ancestors (not all unrelated unbuilt ports).
        full=plan(draft);parents={p["row"]["id"]:p["parents"] for p in full["ports"]}
        while True:
            new={v for k in wanted for v in parents.get(k,[])}
            if new<=wanted:break
            wanted|=new
        result["ports"]=[f for f in draft["ports"] if f["id"] in wanted or f.get("endpoint")]
    return normalize(result)
