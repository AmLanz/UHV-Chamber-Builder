"""Autodesk Fusion adapter. Geometry is prepared before any persistent edits."""
import json
import math
from pathlib import Path
import adsk.core
import adsk.fusion
from . import core

GROUP = "UHVChamberBuilder"
PREVIEW_ID = GROUP+":preview:"
AXIS_COLOR = (0,140,245)
POINT_COLOR = (245,100,20)
MM = 0.1
COLORS = {"metal":(174,184,195),"flange":(214,222,231),"gasket":(190,104,46),
          "fastener":(83,105,129),"tool":(0,132,195),"selected":(255,162,20)}


def pt(x): return adsk.core.Point3D.create(*(float(v)*MM for v in x))
def vec(x): return adsk.core.Vector3D.create(*map(float,x))
def items(collection): return [collection.item(i) for i in range(collection.count)]
def attr(entity, key):
    a=entity.attributes.itemByName(GROUP,key)
    return a.value if a else None
def tag(entity,key,value): entity.attributes.add(GROUP,key,str(value))
def manager(): return adsk.fusion.TemporaryBRepManager.get()


def build_context(design):
    try:intent=design.designIntent
    except AttributeError:return dict(allowed=True,intent="Hybrid (legacy)")
    hybrid=adsk.fusion.DesignIntentTypes.HybridDesignIntentType
    return dict(allowed=intent==hybrid,intent=str(intent),message="Build will ask to switch this document to Hybrid." if intent!=hybrid else "")


def find_chamber(design, ident):
    for occ in items(design.rootComponent.occurrences):
        if attr(occ.component,"chamber_id")==ident:return occ
    return None


def saved_chambers(design):
    return [dict(id=attr(o.component,"chamber_id"),name=o.component.name) for o in items(design.rootComponent.occurrences) if attr(o.component,"chamber_id")]


def load_recipe(design, ident=None):
    available=saved_chambers(design)
    ident=ident or attr(design,"active_recipe") or (available[0]["id"] if available else None)
    occ=find_chamber(design,ident) if ident else None
    raw=attr(occ.component,"recipe") if occ else attr(design,"draft")
    if not raw:return core.new_recipe()
    return core.normalize(json.loads(raw))


def committed_recipe(design, ident):
    occ=find_chamber(design,ident)
    raw=attr(occ.component,"committed") if occ else None
    return core.normalize(json.loads(raw)) if raw else None


def save_recipe(design, recipe):
    data=json.dumps(recipe,allow_nan=False,separators=(",",":"))
    occ=find_chamber(design,recipe["id"])
    tag(occ.component if occ else design,"recipe" if occ else "draft",data)
    tag(design,"active_recipe",recipe["id"])


def primitive_body(spec):
    m=manager();kind=spec["kind"]
    if kind=="sphere":body=m.createSphere(pt(spec["centre"]),spec["radius"]*MM)
    elif kind=="cylinder":
        a=core.add(spec["centre"],core.scale(spec["axis"],spec["lo"]))
        b=core.add(spec["centre"],core.scale(spec["axis"],spec["hi"]))
        body=m.createCylinderOrCone(pt(a),spec["radius"]*MM,pt(b),spec["radius"]*MM)
    else:
        mid=[(a+b)/2 for a,b in zip(spec["lows"],spec["highs"])]
        c=spec["centre"]
        for axis,t in zip(spec["axes"],mid):c=core.add(c,core.scale(axis,t))
        lengths=[(b-a)*MM for a,b in zip(spec["lows"],spec["highs"])]
        obb=adsk.core.OrientedBoundingBox3D.create(pt(c),vec(spec["axes"][0]),vec(spec["axes"][1]),*lengths)
        body=m.createBox(obb)
    if not body:raise core.RecipeError("Fusion could not create a "+kind+" primitive.")
    return body


def cyl(c,n,lo,hi,r):return primitive_body(core.cylinder(c,n,lo,hi,r))
def overlaps(a,b):
    aa,bb=a.boundingBox,b.boundingBox
    return all(getattr(aa.maxPoint,k)>=getattr(bb.minPoint,k)-1e-7 and getattr(bb.maxPoint,k)>=getattr(aa.minPoint,k)-1e-7 for k in "xyz")


def boolean(target,tool,kind,label):
    if kind=="cut" and not overlaps(target,tool):return target
    kinds={"cut":adsk.fusion.BooleanTypes.DifferenceBooleanType,"join":adsk.fusion.BooleanTypes.UnionBooleanType,"intersect":adsk.fusion.BooleanTypes.IntersectionBooleanType}
    if not manager().booleanOperation(target,tool,kinds[kind]):
        raise core.RecipeError("Fusion Boolean failed: "+label+". Inspect tangencies, tiny slivers and attachment extents.")
    return target


def intersection_volume(a,b):
    if not overlaps(a,b):return 0
    aa,bb=a.boundingBox,b.boundingBox
    if any(min(getattr(aa.maxPoint,k),getattr(bb.maxPoint,k))-max(getattr(aa.minPoint,k),getattr(bb.minPoint,k))<1e-8 for k in "xyz"):return 0
    tmp=manager().copy(a)
    if not manager().booleanOperation(tmp,b,adsk.fusion.BooleanTypes.IntersectionBooleanType):
        raise core.RecipeError("Fusion could not evaluate an interference. Adjust a near-tangent connection and retry.")
    return abs(tmp.volume) if tmp and tmp.isValid else 0


def union_many(bodies,label):
    # Keep disjoint lumps as separate bodies; try all connected pairs repeatedly.
    result=[manager().copy(b) for b in bodies]
    changed=True
    while changed:
        changed=False
        for i in range(len(result)):
            for j in range(i+1,len(result)):
                if not overlaps(result[i],result[j]):continue
                trial=manager().copy(result[i])
                if manager().booleanOperation(trial,result[j],adsk.fusion.BooleanTypes.UnionBooleanType):
                    # A union of disjoint solids can be valid but have several lumps.
                    if trial.lumps.count==1:
                        result[i]=trial;result.pop(j);changed=True;break
            if changed:break
    return result


def source_body(design,row,key="token"):
    asset_key="asset" if key=="token" else "cavity_asset"
    if row.get(asset_key):
        path=Path(row[asset_key])
        if not path.is_file():raise core.RecipeError("Imported body asset is missing; relink "+row.get("name","body"),row["id"])
        bs=manager().createFromFile(str(path))
        if not bs or bs.count!=1:raise core.RecipeError("Expected one solid in imported asset.",row["id"])
        return manager().copy(bs.item(0))
    token=row.get(key)
    matches=design.findEntityByToken(token) if token else []
    body=next((adsk.fusion.BRepBody.cast(x) for x in matches if adsk.fusion.BRepBody.cast(x)),None)
    if not body or not body.isSolid:raise core.RecipeError("Selected source solid is missing. Relink "+row.get("name","body"),row["id"])
    native=body.nativeObject or body
    copied=manager().copy(native)
    if body.assemblyContext:
        if not manager().transform(copied,body.assemblyContext.transform2):raise core.RecipeError("Cannot apply source placement.")
    return copied


def flange_bodies(port,defaults,progress=None):
    f=port["dims"];c,n,u,v=port["face"],port["n"],port["u"],port["v"]
    d=f["thickness"];m=manager();eps=0.01
    body=cyl(c,n,-d,0,f["od"]/2)
    boolean(body,cyl(c,n,-d-eps,eps,port["bore"]/2),"cut","flange bore")
    if defaults.get("gasket_features"):
        depth=core.number(defaults["seal_depth"]);tip=core.number(defaults["tip_depth"])
        boolean(body,cyl(c,n,-depth,eps,f["recess"]/2),"cut","schematic seal recess")
        r=f["knife"]/2
        w=min((f["knife"]-port["bore"])/2,(f["recess"]-f["knife"])/2)*0.65
        tip_w=min(0.025,w/4)
        bottom=pt(core.add(c,core.scale(n,-depth-eps)));top=pt(core.add(c,core.scale(n,-tip)))
        tooth=m.createCylinderOrCone(bottom,(r+w)*MM,top,(r+tip_w)*MM)
        inside=m.createCylinderOrCone(bottom,(r-w)*MM,top,(r-tip_w)*MM)
        boolean(tooth,inside,"cut","schematic knife edge")
        boolean(body,tooth,"join","schematic knife edge")
    phase=math.pi/f["bolts"] if port["row"]["configuration"]=="straddled" else 0
    bolt_centres=[]
    for i in range(f["bolts"]):
        if progress and i%8==0:progress("Drilling "+port["row"]["name"]+" · bolt "+str(i+1))
        a=phase+math.tau*i/f["bolts"]
        q=core.add(c,core.add(core.scale(u,f["pcd"]/2*math.cos(a)),core.scale(v,f["pcd"]/2*math.sin(a))))
        bolt_centres.append(q)
        boolean(body,cyl(q,n,-d-eps,eps,f["hole"]/2),"cut","bolt hole")
    result=[]
    if port["row"]["configuration"]=="rotatable":
        # Schematic radial partition; mechanical retaining lip is supplier-specific.
        split_r=(max(port["tube"]["od"],f["recess"])+(f["pcd"]-f["hole"]))/4
        tool=cyl(c,n,-d-eps,eps,split_r)
        insert=m.copy(body);boolean(insert,tool,"intersect","rotatable insert")
        boolean(body,tool,"cut","rotatable bolt ring")
        result += [("Weld ring (schematic)",insert,"flange"),("Rotatable bolt ring",body,"flange")]
    else:result.append(("Flange",body,"flange"))
    if defaults.get("gasket_features"):
        lo,hi=core.gasket_limits(f,defaults);g=cyl(c,n,lo,hi,f["gasket_od"]/2)
        boolean(g,cyl(c,n,lo-eps,hi+eps,f["gasket_id"]/2),"cut","gasket bore")
        result.append(("Nominal gasket",g,"gasket"))
    for i,q in enumerate(bolt_centres):
        if defaults.get("fasteners"):
            bd=core.number(defaults.get("fastener_diameter",0)) or math.floor(f["hole"])
            if bd>=f["hole"]:raise core.RecipeError("Fastener diameter must fit the flange holes.",port["row"]["id"])
            length=max(core.number(defaults["bolt_length"]),d+2*bd)
            shank=cyl(q,n,-length,bd*0.15,bd/2)
            head=cyl(q,n,bd*0.15,bd*0.85,bd*0.9)
            boolean(shank,head,"join","fastener head")
            result.append(("Bolt %02d (schematic)"%(i+1),shank,"fastener"))
            for name,lo,hi in [("Washer",0,bd*0.15),("Nut",-length+bd*0.3,-length+bd*1.1)]:
                ring=cyl(q,n,lo,hi,bd)
                boolean(ring,cyl(q,n,lo-eps,hi+eps,bd*0.51),"cut","fastener bore")
                result.append((name+" %02d (schematic)"%(i+1),ring,"fastener"))
        if defaults.get("tool_clearance"):
            diameter=core.number(defaults["tool_diameter"],"Tool diameter",True)
            length=core.number(defaults["tool_length"],"Tool length",True)
            result.append(("Tool access %02d"%(i+1),cyl(q,n,0,length,diameter/2),"tool"))
    return result


def prepare(design,recipe,progress=None):
    plan=core.plan(recipe);r=plan["recipe"];outer=[];void=[];diagnostics=[];port_outer={};port_void={}
    for p in plan["primitives"]:
        row=p["row"]
        if progress:progress("Preparing "+row["name"])
        if p["outer"]:
            outer.append(primitive_body(p["outer"]));void.append(primitive_body(p["void"]))
        else:
            outer.append(source_body(design,row))
            if row.get("cavity_token") or row.get("cavity_asset"):void.append(source_body(design,row,"cavity_token"))
            diagnostics.append(dict(row=row["id"],level="warning",message="Imported material: use bounded manual necks; automatic cavity attachment is available for generated shapes/tubes."))
    for p in plan["ports"]:
        if p["outer"]:
            po=primitive_body(p["outer"]);pv=primitive_body(p["void"])
            outer.append(po);void.append(pv);port_outer[p["row"]["id"]]=po;port_void[p["row"]["id"]]=pv
    if progress:progress("Combining main-chamber volumes")
    main=union_many(outer,"main chamber")
    for b in main:
        for tool in void:boolean(b,tool,"cut","vacuum cavity")
        if not b.isSolid or b.volume<=1e-10:raise core.RecipeError("A cavity removed the entire chamber wall or produced invalid geometry.")
    if len(main)!=1 or main[0].lumps.count!=1:
        raise core.RecipeError("Main chamber is disconnected. Overlap the body shapes/neck material or correct the manual connection extent.")
    if len(union_many(void,"vacuum connectivity"))>1:
        diagnostics.append(dict(row="",level="warning",message="The cavity tools form more than one isolated volume. Inspect for a hidden diaphragm or a manual neck that stops in the wall."))
    entries={"main":dict(name="Main chamber",bodies=[("Main chamber",main[0],"metal")],signature=core.fingerprint(dict(primitives=plan["primitives"],necks=[{k:p[k] for k in ("outer","void")} for p in plan["ports"]])))}
    for p in plan["ports"]:
        if progress:progress("Creating "+p["row"]["name"])
        # Documentation numbers do not change geometry or face identities.
        geometry_port=dict(p,row={k:v for k,v in p["row"].items() if k!="number"})
        bodies=flange_bodies(p,r["defaults"],progress)
        entries[p["row"]["id"]]=dict(name=p["row"]["name"],bodies=[b for b in bodies if b[2]!="gasket"],gasket_bodies=[b for b in bodies if b[2]=="gasket"],signature=core.fingerprint(dict(port=geometry_port,layout="gasket-component-outer-face-v1",options={k:v for k,v in r["defaults"].items() if k not in ("flanges","tubes","preferred_tubes","theme","show_points","show_axes","gap","proximity_check")})))
    uncertain=False
    def measure(a,b):
        nonlocal uncertain
        try:return intersection_volume(a,b)
        except (core.RecipeError,RuntimeError):
            uncertain=True;return 0
    ids=list(port_outer)
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            if measure(port_outer[a],port_outer[b])>1e-8:
                connected=measure(port_void[a],port_void[b])>1e-8
                for x,y in [(a,b),(b,a)]:diagnostics.append(dict(row=x,other=y,level="merge" if connected else "warning",message="Necks merge" if connected else "Necks touch/overlap but their passages are isolated"))
    ports=plan["ports"]
    for i,a in enumerate(ports):
        solids_a=[x[1] for x in entries[a["row"]["id"]]["bodies"] if x[2]=="flange"]
        for sa in solids_a:
            if measure(sa,main[0])>1e-7:
                diagnostics.append(dict(row=a["row"]["id"],level="warning",message="Flange overlaps main-chamber metal. Inspect the face position and neck layout."))
        for b in ports[i+1:]:
            solids_b=[x[1] for x in entries[b["row"]["id"]]["bodies"] if x[2]=="flange"]
            clash=any(measure(sa,sb)>1e-7 for sa in solids_a for sb in solids_b)
            if clash:
                for x,y in [(a,b),(b,a)]:diagnostics.append(dict(row=x["row"]["id"],other=y["row"]["id"],level="warning",message="Flange collision with "+y["row"]["name"]))
            elif r["defaults"].get("proximity_check"):
                for sa in solids_a:
                    for sb in solids_b:
                        measured=adsk.core.Application.get().measureManager.measureMinimumDistance(sa,sb)
                        if measured and measured.value/MM<core.number(r["defaults"]["gap"]):
                            for x,y in [(a,b),(b,a)]:diagnostics.append(dict(row=x["row"]["id"],other=y["row"]["id"],level="warning",message="Flange gap below project threshold"))
    if uncertain:diagnostics.append(dict(row="",level="warning",message="Some kernel interference tests could not be completed. Inspect the layout; those tests are not reported as passed."))
    return dict(plan=plan,entries=entries,diagnostics=diagnostics)


def appearance(app,design,kind):
    name=GROUP+" "+kind;existing=design.appearances.itemByName(name)
    if existing:return existing
    library=app.materialLibraries.itemById("BA5EE55E-9982-449B-9D66-9F036540E140")
    source=library.appearances.itemById("Prism-093") if library else None
    if not source:return None
    appn=design.appearances.addByCopy(source,name)
    prop=adsk.core.ColorProperty.cast(appn.appearanceProperties.itemById("opaque_albedo"))
    if prop:prop.value=adsk.core.Color.create(*COLORS[kind],255)
    return appn


def add_bodies(app,design,component,entries):
    base=None
    if design.designType==adsk.fusion.DesignTypes.ParametricDesignType:
        base=component.features.baseFeatures.add();base.name="UHV geometry";tag(base,"managed","1")
        if not base.startEdit():raise core.RecipeError("Cannot edit geometry base feature.")
    start=0 if base else component.bRepBodies.count
    try:
        for name,body,kind in entries:
            made=component.bRepBodies.add(body,base) if base else component.bRepBodies.add(body)
            if not made:raise core.RecipeError("Cannot persist body: "+name)
            made.name=name
    finally:
        if base and not base.finishEdit():raise core.RecipeError("Cannot finish geometry base feature.")
    collection=base.bodies if base else component.bRepBodies
    for i,(name,body,kind) in enumerate(entries):
        made=collection.item(start+i);made.name=name;tag(made,"kind",kind)
        appn=appearance(app,design,kind)
        if appn:made.appearance=appn
        if kind=="tool":made.opacity=0.18


def clear_managed_geometry(component):
    for base in reversed(items(component.features.baseFeatures)):
        if attr(base,"managed"):base.deleteMe()
    for body in reversed(items(component.bRepBodies)):
        if attr(body,"kind"):body.deleteMe()


def make_datums(component,recipe,ports):
    # A 3D sketch supplies parametric-safe points for construction geometry.
    for axis in reversed(items(component.constructionAxes)):
        if attr(axis,"managed"):axis.deleteMe()
    for point in reversed(items(component.constructionPoints)):
        if attr(point,"managed"):point.deleteMe()
    for sketch in reversed(items(component.sketches)):
        if attr(sketch,"managed"):sketch.deleteMe()
    sketch=component.sketches.add(component.xYConstructionPlane);sketch.name="UHV datum definitions";tag(sketch,"managed","1")
    for row in recipe["points"]:
        sp=sketch.sketchPoints.add(pt(core.lookup_point(recipe,row["id"])))
        inp=component.constructionPoints.createInput();inp.setByPoint(sp)
        cp=component.constructionPoints.add(inp);cp.name=row["name"];tag(cp,"managed",row["id"])
        cp.isLightBulbOn=bool(recipe["defaults"]["show_points"] and row.get("visible",True))
    for p in ports:
        a=sketch.sketchPoints.add(pt(p["face"]));b=sketch.sketchPoints.add(pt(core.add(p["face"],core.scale(p["n"],20))))
        inp=component.constructionAxes.createInput();inp.setByTwoPoints(a,b)
        axis=component.constructionAxes.add(inp);axis.name=p["row"]["name"]+" centre axis";tag(axis,"managed",p["row"]["id"])
        axis.isLightBulbOn=bool(recipe["defaults"]["show_axes"])
    sketch.isLightBulbOn=False


def place_child_at_chamber(child,chamber):
    """Only a proxy rooted in the design may receive a nested pose override."""
    proxy=child.createForAssemblyContext(chamber)
    if not proxy or proxy.assemblyContext is None:raise core.RecipeError("Cannot resolve the chamber's root assembly context.")
    expected=chamber.transform2.copy()
    def matches():return all(abs(a-b)<1e-8 for a,b in zip(proxy.transform2.asArray(),expected.asArray()))
    if matches():return False
    if getattr(proxy,"isGroundToParent",False):proxy.isGroundToParent=False
    proxy.transform2=expected
    if not matches():raise core.RecipeError("Fusion did not retain the flange placement. Build cancelled.")
    return True


def is_gasket(occurrence):
    return attr(occurrence.component,"role")=="gasket"


def has_manual_content(component):
    if any(not attr(b,"kind") for b in items(component.bRepBodies)):return True
    return any(not is_gasket(o) or has_manual_content(o.component) for o in items(component.occurrences))


def sync_gasket(app,design,flange,chamber,entry):
    """One independently visible gasket component under its flange."""
    existing=[o for o in items(flange.component.occurrences) if is_gasket(o)]
    bodies=entry.get("gasket_bodies",[])
    if not bodies:
        for o in existing:
            if has_manual_content(o.component):raise core.RecipeError("Gasket contains manual geometry. Move or remove it before disabling gasket features.")
            o.deleteMe()
        return False
    if len(existing)>1:raise core.RecipeError("This flange has duplicate gasket components. Remove the extra copy before rebuilding.")
    gasket=existing[0] if existing else flange.component.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    tag(gasket.component,"role","gasket");gasket.component.name="Gasket"
    # A third-level child needs the flange proxy rooted through the chamber.
    moved=place_child_at_chamber(gasket,flange.createForAssemblyContext(chamber))
    owned=[b for b in items(gasket.component.bRepBodies) if attr(b,"kind")]
    if attr(gasket.component,"signature")!=entry["signature"] or len(owned)!=len(bodies):
        clear_managed_geometry(gasket.component);add_bodies(app,design,gasket.component,bodies)
        tag(gasket.component,"signature",entry["signature"])
    return moved


def commit(app,design,prepared,draft,convert_to_hybrid=False):
    if not build_context(design)["allowed"] and not convert_to_hybrid:raise core.RecipeError("Build requires confirmation to switch this document to Hybrid.")
    problems=[d for d in prepared["diagnostics"] if d["level"]=="error"]
    if problems:raise core.RecipeError(problems[0]["message"],problems[0]["row"])
    if design.activeOccurrence and not design.activateRootComponent():raise core.RecipeError("Activate the root component and retry the build.")
    if not build_context(design)["allowed"]:
        design.designIntent=adsk.fusion.DesignIntentTypes.HybridDesignIntentType
        if not build_context(design)["allowed"]:raise core.RecipeError("Fusion could not switch this document to Hybrid. Change its design type in Fusion and retry.")
    recipe=prepared["plan"]["recipe"];occ=find_chamber(design,recipe["id"])
    if not occ:
        occ=design.rootComponent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        tag(occ.component,"chamber_id",recipe["id"])
    comp=occ.component;comp.name=recipe.get("name","UHV chamber")
    pending_position=False
    existing={attr(o.component,"row_id"):o for o in items(comp.occurrences) if attr(o.component,"row_id")}
    for ident,entry in prepared["entries"].items():
        child=existing.get(ident)
        if not child:
            child=comp.occurrences.addNewComponent(adsk.core.Matrix3D.create());tag(child.component,"row_id",ident)
        # All generated child placements stay at the chamber frame.
        pending_position=place_child_at_chamber(child,occ) or pending_position
        child.component.name=entry["name"]
        row=next((r for r in recipe["ports"] if r["id"]==ident),None)
        if row:tag(child.component,"flange_number",row.get("number",""))
        owned=[b for b in items(child.component.bRepBodies) if attr(b,"kind")]
        if attr(child.component,"signature")!=entry["signature"] or len(owned)!=len(entry["bodies"]):
            clear_managed_geometry(child.component)
            add_bodies(app,design,child.component,entry["bodies"])
            tag(child.component,"signature",entry["signature"])
        if row:pending_position=sync_gasket(app,design,child,occ,entry) or pending_position
    for ident,child in existing.items():
        if ident not in prepared["entries"]:
            if has_manual_content(child.component):raise core.RecipeError("Removed port contains manual bodies. Move or explicitly delete these before rebuilding: "+child.component.name)
            child.deleteMe()
    if pending_position and design.designType==adsk.fusion.DesignTypes.ParametricDesignType and design.snapshots.hasPendingSnapshot:
        if not design.snapshots.add():raise core.RecipeError("Fusion could not capture the flange placements.")
    datum_signature=core.fingerprint(dict(points=recipe["points"],ports=[dict(face=p["face"],n=p["n"],id=p["row"]["id"],name=p["row"]["name"]) for p in prepared["plan"]["ports"]]))
    managed_points=[p for p in items(comp.constructionPoints) if attr(p,"managed")]
    managed_axes=[a for a in items(comp.constructionAxes) if attr(a,"managed")]
    if (attr(comp,"datum_signature")!=datum_signature or len(managed_points)!=len(recipe["points"])
            or len(managed_axes)!=len(prepared["plan"]["ports"])):
        make_datums(comp,recipe,prepared["plan"]["ports"]);tag(comp,"datum_signature",datum_signature)
    else:
        visibility={r["id"]:r.get("visible",True) for r in recipe["points"]}
        for p in managed_points:p.isLightBulbOn=bool(recipe["defaults"]["show_points"] and visibility.get(attr(p,"managed"),True))
        for a in managed_axes:a.isLightBulbOn=bool(recipe["defaults"]["show_axes"])
    tag(comp,"committed",json.dumps(recipe,allow_nan=False,separators=(",",":")))
    tag(comp,"build_fingerprint",core.fingerprint(recipe));save_recipe(design,draft)
    return state(design,draft)


def legacy_preview(group):
    """Recognize the untagged, flat body/line groups drawn by older releases.

    Require UHV's exact palette, line style and both body and datum graphics;
    never remove arbitrary blue lines or another add-in's named group.
    """
    if group.id or group.name not in ("","Custom Graphics"):return False
    bodies=0;datums=0
    for entity in items(group):
        effect=adsk.fusion.CustomGraphicsSolidColorEffect.cast(entity.color)
        if not effect:return False
        c=effect.color;rgb=(c.red,c.green,c.blue)
        if entity.objectType==adsk.fusion.CustomGraphicsBRepBody.classType():
            if rgb not in COLORS.values():return False
            bodies+=1
        elif entity.objectType==adsk.fusion.CustomGraphicsLines.classType():
            if rgb not in (AXIS_COLOR,POINT_COLOR) or abs(entity.weight-2)>1e-8:return False
            datums+=1
        else:return False
    return bodies>0 and datums>0


def clear_preview_graphics(design,include_legacy=False):
    removed=0
    for group in reversed(items(design.rootComponent.customGraphicsGroups)):
        try:owned=group.id.startswith(PREVIEW_ID) or (include_legacy and legacy_preview(group))
        except (RuntimeError,AttributeError):continue
        if owned:
            if not group.deleteMe():raise core.RecipeError("Fusion could not remove a UHV preview group. Close and reopen this document, then retry Clear preview.")
            removed+=1
    return removed


def preview(design,prepared,selected=None):
    clear_preview_graphics(design,include_legacy=True)
    root=design.rootComponent;group=root.customGraphicsGroups.add()
    try:
        group.id=PREVIEW_ID+prepared["plan"]["recipe"]["id"];group.name="UHV chamber preview"
        group.isChildrenSelectable=False;group.isSelectable=False
        recipe=prepared["plan"]["recipe"];occ=find_chamber(design,recipe["id"])
        if occ:group.transform=occ.transform2
        for ident,entry in prepared["entries"].items():
            for _,body,kind in entry["bodies"]+entry.get("gasket_bodies",[]):
                g=group.addBRepBody(body)
                color=COLORS["selected"] if ident==selected else COLORS[kind]
                g.color=adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*color,255))
                g.setOpacity(0.15 if kind=="tool" else 0.65 if selected and ident!=selected else 0.95,True)
        def line(a,b,color):
            coords=adsk.fusion.CustomGraphicsCoordinates.create([v*MM for p in (a,b) for v in p])
            g=group.addLines(coords,[],False);g.color=adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*color,255));g.weight=2
        if recipe["defaults"]["show_axes"]:
            for p in prepared["plan"]["ports"]:line(p["point"],core.add(p["face"],core.scale(p["n"],25)),AXIS_COLOR)
        if recipe["defaults"]["show_points"]:
            for row in recipe["points"]:
                if not row.get("visible",True):continue
                p=core.lookup_point(recipe,row["id"])
                for axis in ((1,0,0),(0,1,0),(0,0,1)):line(core.add(p,core.scale(axis,-2)),core.add(p,core.scale(axis,2)),POINT_COLOR)
        return group
    except Exception:group.deleteMe();raise


def state(design,draft):
    occ=find_chamber(design,draft["id"]);old=committed_recipe(design,draft["id"]);statuses={}
    rows={r["id"]:r for key in ("bodies","ports") for r in (old or {}).get(key,[])}
    children={attr(o.component,"row_id"):o for o in items(occ.component.occurrences)} if occ else {}
    shared_changed=bool(old and (old["defaults"]!=draft["defaults"] or old["points"]!=draft["points"]))
    for key in ("bodies","ports"):
        for row in draft[key]:
            ident=row["id"];child=children.get("main" if key=="bodies" else ident)
            count=len([b for b in items(child.component.bRepBodies) if attr(b,"kind")]) if child else 0
            expected=1;gasket_ok=True
            if key=="ports" and ident in rows:
                previous=rows[ident];d=old["defaults"];n=core.flange_values(old,previous)["bolts"]
                expected=(2 if previous.get("configuration")=="rotatable" else 1)+n*(3*int(bool(d["fasteners"]))+int(bool(d["tool_clearance"])))
                gaskets=[o for o in items(child.component.occurrences) if is_gasket(o)] if child else []
                gasket_ok=(len(gaskets)==1 and len([b for b in items(gaskets[0].component.bRepBodies) if attr(b,"kind")=="gasket"])==1) if d["gasket_features"] else not gaskets
            statuses[ident]="Suppressed" if not row.get("enabled",True) else "Not built" if ident not in rows else "Missing geometry" if count!=expected or not gasket_ok else "Changed" if shared_changed or row!=rows[ident] else "Up to date"
    return dict(statuses=statuses,saved=saved_chambers(design),inventory=inventory(design,draft),build_context=build_context(design))


def inventory(design,draft):
    result=[];occ=find_chamber(design,draft["id"])
    # Root occurrences outside the recipe and untagged bodies within it.
    for o in items(design.rootComponent.occurrences):
        if o!=occ:result.append(dict(name=o.component.name,token=o.entityToken,kind="Other component",owned=False))
    for b in items(design.rootComponent.bRepBodies):result.append(dict(name=b.name,token=b.entityToken,kind="Other body",owned=False))
    if occ:
        wanted={"main"}|{f["id"] for f in draft["ports"] if f.get("enabled",True)}
        for o in [occ]+items(occ.component.occurrences):
            if o!=occ and attr(o.component,"row_id") not in wanted:
                result.append(dict(name=o.component.name,token=o.entityToken,kind="Removed/suppressed row" if attr(o.component,"row_id") else "Unmanaged component",owned=False))
                continue
            if o!=occ:
                for child in items(o.component.occurrences):
                    if not is_gasket(child) or has_manual_content(child.component):result.append(dict(name=o.component.name+" / "+child.component.name,token=child.entityToken,kind="Unmanaged content" if is_gasket(child) else "Unmanaged component",owned=False))
            for b in items(o.component.bRepBodies):
                if not attr(b,"kind"):result.append(dict(name=o.component.name+" / "+b.name,token=b.entityToken,kind="Unmanaged body",owned=False))
    return result


def select_entity(design,token):
    matches=design.findEntityByToken(token)
    if not matches:raise core.RecipeError("Geometry no longer exists. Refresh the list.")
    entity=matches[0];ui=adsk.core.Application.get().userInterface;ui.activeSelections.clear();ui.activeSelections.add(entity)
    return entity
