"""Run from the parent folder: python -m unittest discover -s UHVChamberBuilder/tests -v"""
from copy import deepcopy
from pathlib import Path
import json
import math
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from UHVChamberBuilder import core, exchange


def branch_recipe(equal=False):
    r=core.new_recipe();a=r["points"][0];b=core.new_point("B",(150,0,0));r["points"].append(b)
    body=core.new_body(a["id"]);r["bodies"]=[body]
    parent=core.new_port(a["id"]);parent.update(name="Large neck",preset="DN100CF",distance=230)
    child=core.new_port(b["id"]);child.update(name="Side branch",azimuth=90,distance=150,
        target=parent["id"],preset="DN100CF" if equal else "DN40CF")
    r["ports"]=[child,parent]
    return r,parent,child


class Coordinates(unittest.TestCase):
    def test_azimuth_ring_matches_requested_angles(self):
        source=Path(__file__).resolve().parents[1]/"examples/Azimuth_symmetry.json"
        r=json.loads(source.read_text());plan=core.plan(r)
        ports=sorted(plan["ports"],key=lambda p:float(p["row"]["azimuth"]))
        self.assertEqual([p["row"]["azimuth"] for p in ports],[-75,-45,-15,15,45,75])
        for p in ports:
            face=p["face"];self.assertAlmostEqual(math.hypot(face[0],face[1]),160)
            self.assertAlmostEqual(face[2],0)
            self.assertAlmostEqual(math.degrees(math.atan2(face[1],face[0])),p["row"]["azimuth"])
            self.assertAlmostEqual(p["length"],ports[0]["length"])
        for a,b in zip(ports,ports[1:]):self.assertAlmostEqual(core.dot(a["n"],b["n"]),math.cos(math.radians(30)))
        for a,b in zip(ports,reversed(ports)):
            self.assertAlmostEqual(a["face"][0],b["face"][0]);self.assertAlmostEqual(a["face"][1],-b["face"][1])

    def test_azimuth_tilts_from_x_and_elevation_sweeps_around_x(self):
        for elevation in [-75,-45,-15,0,15,45,75,90]:
            for azimuth in [-75,-45,-15,15,45,75]:
                _,_,n=core.frame(azimuth,elevation,38)
                self.assertAlmostEqual(n[0],math.cos(math.radians(abs(azimuth))))
                self.assertAlmostEqual(math.hypot(n[1],n[2]),math.sin(math.radians(abs(azimuth))))
                self.assertEqual(n,core.frame(azimuth,elevation,0)[2])
                if azimuth>0:self.assertAlmostEqual(math.degrees(math.atan2(n[2],n[1])),elevation)

    def test_gasket_outer_face_offset_and_allowed_overlap(self):
        r=core.example_recipe();r["defaults"]["gasket_features"]=True
        dims=core.flange_values(r,r["ports"][1]);thickness=dims["gasket_t"]
        for offset in [0,0.5,2,5,-1]:
            r["defaults"]["gasket_standoff"]=offset
            self.assertFalse(core.validate(r)["errors"])
            lo,hi=core.gasket_limits(dims,r["defaults"])
            self.assertEqual(hi,offset);self.assertEqual(hi-lo,thickness)
            if offset<thickness:self.assertLess(lo,0)

    def test_cardinal_directions_and_poles(self):
        for az,el,n in [(0,0,(1,0,0)),(90,0,(0,1,0)),(-90,0,(0,-1,0)),(180,0,(-1,0,0)),(0,90,(1,0,0)),(90,90,(0,0,1)),(90,-90,(0,0,-1))]:
            u,v,got=core.frame(az,el)
            for x,y in zip(got,n):self.assertAlmostEqual(x,y)
            self.assertAlmostEqual(core.dot(u,v),0)
            self.assertAlmostEqual(core.dot(core.cross(u,v),got),1)

    def test_roll_and_units(self):
        u,v,n=core.frame(0,0,90)
        self.assertAlmostEqual(u[2],1);self.assertAlmostEqual(v[1],-1)
        self.assertEqual(core.number("2,5"),2.5)
        for bad in ("NaN","Infinity",True,"bad"):
            with self.assertRaises(core.RecipeError):core.number(bad)
        with self.assertRaises(core.RecipeError):core.frame(181,0)

    def test_mating_plane_and_bore_independence(self):
        r=core.example_recipe();f=r["ports"][1];f["bore"]=30
        p=next(p for p in core.plan(r)["ports"] if p["row"]["id"]==f["id"])
        self.assertAlmostEqual(p["face"][1],160)
        self.assertAlmostEqual(core.norm(core.sub(p["face"],p["back"])),12.5)
        self.assertEqual(p["bore"],30)
        self.assertEqual(p["void"]["radius"],17.5)  # Neck keeps its actual tube ID.

    def test_toward_point_direction(self):
        r=core.example_recipe();b=core.new_point("B",(100,100,0));r["points"].append(b)
        r["ports"][0]["toward"]=b["id"]
        x=core.validate(r)["resolved"][r["ports"][0]["id"]]
        self.assertAlmostEqual(x["n"][0],math.sqrt(.5));self.assertAlmostEqual(x["n"][1],math.sqrt(.5))


class XAxisRing(unittest.TestCase):
    def recipe(self):
        return json.loads((Path(__file__).resolve().parents[1]/"examples/X_axis_ring.json").read_text())

    def rotate_x(self,p,degrees):
        c,s=math.cos(math.radians(degrees)),math.sin(math.radians(degrees))
        return p[0],c*p[1]-s*p[2],s*p[1]+c*p[2]

    def assertVectorClose(self,a,b):
        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=10)

    def ring(self,plan):
        def angle(p):
            f=p["row"];return (f["elevation"] if f["azimuth"]>=0 else 180-f["elevation"])%360
        return sorted((p for p in plan["ports"] if not p["row"].get("endpoint")),key=angle)

    def test_exact_reported_case_full_frame_rotates_about_x(self):
        r=self.recipe()
        for f in r["ports"]:f["roll"]=23.5
        ports=self.ring(core.plan(r));self.assertEqual(len(ports),12)
        centre=next(p for p in r["points"] if p["name"]=="B")
        for p,q in zip(ports,ports[1:]+ports[:1]):
            self.assertAlmostEqual(p["face"][0]-centre["x"],160*math.cos(math.radians(75)))
            self.assertAlmostEqual(p["length"],ports[0]["length"])
            for key in ("face","back","n","u","v"):
                self.assertVectorClose(self.rotate_x(p[key],30),q[key])
            self.assertVectorClose(self.rotate_x(p["outer"]["centre"],30),q["outer"]["centre"])
            self.assertAlmostEqual(core.dot(p["u"],p["n"]),0)
            self.assertVectorClose(core.cross(p["u"],p["v"]),p["n"])

    def test_previous_formula_reproduces_the_failure_and_90_degree_special_case(self):
        for az,expected_error in [(75,11.059183838299946),(90,0)]:
            def old_normal(e):
                azimuth,elevation=map(math.radians,(az,e))
                return math.cos(elevation)*math.cos(azimuth),math.cos(elevation)*math.sin(azimuth),math.sin(elevation)
            a,b=old_normal(15),old_normal(45)
            self.assertAlmostEqual(160*core.norm(core.sub(self.rotate_x(a,30),b)),expected_error)

    def test_full_sweep_and_negative_tilt_half_are_equivalent(self):
        for sweep in [-75,-45,-15,15,45,75]:
            for got,want in zip(core.frame(-75,sweep,17),core.frame(75,180-sweep,17)):
                self.assertVectorClose(got,want)
        for got,want in zip(core.frame(75,375),core.frame(75,15)):self.assertVectorClose(got,want)
        self.assertVectorClose(core.frame(0,90)[2],(1,0,0))
        self.assertVectorClose(core.frame(90,90)[2],(0,0,1))
        with self.assertRaises(core.RecipeError):core.frame(181,0)

    def test_body_and_tube_end_flange_share_the_new_axis(self):
        r=self.recipe();r["bodies"][0].update(azimuth=75,elevation=45)
        checked=core.validate(r);axis=core.frame(75,45)[2]
        self.assertVectorClose(checked["primitives"][0]["axes"][2],axis)
        for f in r["ports"]:
            if f.get("endpoint"):
                n=checked["resolved"][f["id"]]["n"]
                self.assertVectorClose(n,core.scale(axis,-1 if f["endpoint"]["end"]=="minus" else 1))

    def test_obsolete_mode_is_discarded_and_only_x_axis_math_is_used(self):
        r=core.example_recipe();r["defaults"]["flange_angle_mode"]="azimuth_elevation"
        loaded=core.normalize(r)
        self.assertNotIn("flange_angle_mode",loaded["defaults"])
        self.assertVectorClose(core.validate(loaded)["resolved"][r["ports"][2]["id"]]["n"],(0,0,1))

    def test_aim_toward_point_preserves_its_normal(self):
        r=self.recipe();p=core.new_point("C",(70,-20,40));r["points"].append(p)
        f=next(f for f in r["ports"] if not f.get("endpoint"));f["toward"]=p["id"]
        self.assertVectorClose(core.validate(r)["resolved"][f["id"]]["n"],core.unit((50,-20,40)))

    def test_angle_convention_survives_export_import(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.recipe();path=Path(td)/"ring.zip";exchange.export_bundle(r,path)
            loaded=exchange.import_recipe(path,Path(td))
            self.assertNotIn("flange_angle_mode",loaded["defaults"])
            self.assertEqual(core.plan(loaded),core.plan(r))
            self.assertIn("Azimuth from X / elevation around X",exchange.report(loaded))


class Recipes(unittest.TestCase):
    def test_stock_catalog_invariants(self):
        self.assertEqual(len(core.CATALOG["flanges"]),16)
        self.assertEqual(len(core.CATALOG["tubes"]),12)
        self.assertEqual(core.CATALOG["flanges"]["DN250CF"]["od"],304.8)
        r=core.new_recipe();f=core.new_port(r["points"][0]["id"])
        for preset in core.CATALOG["flanges"]:
            f["preset"]=preset;d=core.flange_values(r,f)
            self.assertLess(d["knife"],d["recess"])
            self.assertLess(d["gasket_od"],d["recess"])
        for preset in core.CATALOG["tubes"]:
            f["tube"]=preset;t=core.tube_values(r,f)
            self.assertGreater(t["id"],0)

    def test_global_defaults_and_explicit_override(self):
        r=core.example_recipe();f=r["ports"][1]
        f["deviate"]=True;f["overrides"]={"od":72}
        r["defaults"]["flanges"]["DN40CF"].update(od=71,thickness=13)
        d=core.flange_values(r,f);self.assertEqual(d["od"],72);self.assertEqual(d["thickness"],13)
        self.assertEqual(core.flange_values(r,r["ports"][2])["od"],71)

    def test_custom_and_alias(self):
        r=core.example_recipe();f=r["ports"][0]
        f.update(preset="Custom",overrides=deepcopy(core.CATALOG["flanges"]["DN40CF"]))
        r["defaults"]["flanges"]["DN40CF"]["od"]=80
        self.assertEqual(core.flange_values(r,f)["od"],69.9)
        f["preset"]="DN150CF";f["overrides"]={};f["deviate"]=False
        r=core.normalize(r);self.assertEqual(r["ports"][0]["preset"],"DN160CF")
        self.assertEqual(core.tube_values(r,r["ports"][0])["od"],154)

    def test_missing_point_marks_rows(self):
        r=core.example_recipe();r["points"]=[]
        checked=core.validate(r)
        self.assertEqual({x["row"] for x in checked["errors"]},{x["id"] for x in r["bodies"]+r["ports"]})

    def test_ids_and_schema(self):
        r=core.new_recipe();r["points"].append(deepcopy(r["points"][0]))
        with self.assertRaisesRegex(core.RecipeError,"duplicate"):core.normalize(r)
        for change in ({"schema":2},{"units":"cm"},{"defaults":[]},{"points":["invalid"]}):
            r=core.new_recipe();r.update(change)
            with self.assertRaises(core.RecipeError):core.normalize(r)

    def test_invalid_dimensions(self):
        r=core.example_recipe();f=r["ports"][0];f.update(deviate=True,overrides={"bolts":6.5})
        self.assertTrue(core.validate(r)["errors"])
        f.update(overrides={},tube="Custom",tube_diameter=2,tube_wall=2)
        self.assertTrue(core.validate(r)["errors"])

    def test_sphere_and_box_different_walls(self):
        r=core.new_recipe();p=r["points"][0]["id"]
        s=core.new_body(p);s.update(diameter=100,wall=2)
        b=core.new_body(p,"box");b["wall"]=5
        r["bodies"]=[s,b];plan=core.plan(r)
        self.assertEqual(plan["primitives"][0]["outer"]["radius"],52)
        cube=plan["primitives"][1]
        self.assertEqual(cube["outer"]["lows"],(-105,-80,-80))
        self.assertEqual(cube["void"]["lows"],(-100,-75,-75))

    def test_tube_end_flange_and_plate(self):
        r=core.new_recipe();b=core.new_body(r["points"][0]["id"],"tube")
        b.update(end_minus="plate",cap_minus=5,end_plus="flange");r["bodies"]=[b]
        plan=core.plan(r);shape=plan["primitives"][0]
        self.assertAlmostEqual(shape["outer"]["hi"],76)
        self.assertAlmostEqual(shape["void"]["lo"],-95,places=3)
        f=plan["ports"][0];self.assertEqual(f["face"],(100,0,0));self.assertEqual(f["tube"]["od"],206)
        self.assertIsNone(f["outer"])
        stable=core.normalize(plan["recipe"]);self.assertEqual(stable,core.normalize(stable))
        stable["bodies"][0]["end_plus"]="open"
        self.assertFalse(core.normalize(stable)["ports"])

    def test_both_end_normals(self):
        r=core.new_recipe();b=core.new_body(r["points"][0]["id"],"tube")
        b.update(end_minus="flange",end_plus="flange",azimuth=90,elevation=90);r["bodies"]=[b]
        ends=core.plan(r)["ports"]
        self.assertAlmostEqual(ends[0]["n"][2]*ends[1]["n"][2],-1)


class FlangeNumbers(unittest.TestCase):
    def test_new_and_legacy_rows_start_blank(self):
        r=core.example_recipe()
        for f in r["ports"]:f.pop("number")
        ids=[f["id"] for f in r["ports"]]
        loaded=core.normalize(r)
        self.assertEqual([f["number"] for f in loaded["ports"]],["","",""])
        self.assertEqual([f["id"] for f in loaded["ports"]],ids)
        self.assertEqual(core.new_port(r["points"][0]["id"])["number"],"")

    def test_gaps_and_manual_order_are_preserved(self):
        r=core.example_recipe()
        for f,n in zip(r["ports"],["6","1","5"]):f["number"]=n
        core.require_flange_numbers(r)
        self.assertFalse(core.validate(r)["errors"])
        self.assertEqual([f["number"] for f in core.normalize(r)["ports"]],["6","1","5"])

    def test_preview_allows_blank_but_build_requires_number(self):
        r=core.example_recipe();r["ports"][1]["number"]=""
        self.assertFalse(core.validate(r)["errors"])
        self.assertEqual(len(core.plan(r)["ports"]),3)
        with self.assertRaises(core.RecipeError) as caught:core.require_flange_numbers(r)
        self.assertEqual(caught.exception.row_id,r["ports"][1]["id"])
        r["ports"][1]["enabled"]=False
        core.require_flange_numbers(r)

    def test_duplicate_and_invalid_numbers_mark_the_rows(self):
        r=core.example_recipe();r["ports"][1]["number"]="01"
        self.assertEqual({x["row"] for x in core.number_errors(r)},{r["ports"][0]["id"],r["ports"][1]["id"]})
        for value in ["0","-1","1.5","2e3",True,"abc"]:
            with self.subTest(value=value),self.assertRaises(core.RecipeError):core.flange_number(value)

    def test_endpoint_numbers_and_order_survive_normalization(self):
        r=core.new_recipe();b=core.new_body(r["points"][0]["id"],"tube")
        b.update(end_minus="flange",end_plus="flange");r["bodies"]=[b]
        r=core.normalize(r)
        self.assertEqual([f["number"] for f in r["ports"]],["",""])
        r["ports"].reverse()
        for f,n in zip(r["ports"],["8","3"]):f["number"]=n
        self.assertEqual(core.normalize(r)["ports"],r["ports"])

    def test_numbers_and_order_in_portable_documentation(self):
        with tempfile.TemporaryDirectory() as td:
            r=core.example_recipe()
            for f,n in zip(r["ports"],["6","2","5"]):f["number"]=n
            p=Path(td)/"chamber.zip";exchange.export_bundle(r,p)
            self.assertEqual(exchange.import_recipe(p,Path(td))["ports"],r["ports"])
            with zipfile.ZipFile(p) as z:
                import csv,io
                rows=list(csv.DictReader(io.StringIO(z.read("flanges.csv").decode("utf-8-sig"))))
                self.assertEqual([f["number"] for f in rows],["6","2","5"])
                self.assertIn("| 6 | Pump |",z.read("report.md").decode())


class Connections(unittest.TestCase):
    def test_example_connects(self):
        plan=core.plan(core.example_recipe())
        self.assertEqual(len(plan["ports"]),3)
        self.assertTrue(all(p["length"]>0 for p in plan["ports"]))

    def test_branch_order_independence(self):
        r,parent,child=branch_recipe();a=core.plan(r)
        r["ports"].reverse();self.assertEqual(a,core.plan(r)|{"recipe":a["recipe"]})
        c=next(p for p in a["ports"] if p["row"]["id"]==child["id"])
        self.assertEqual(c["parents"],[parent["id"]]);self.assertGreater(c["length"],80)

    def test_equal_diameter_tee(self):
        r,parent,child=branch_recipe(equal=True)
        c=next(p for p in core.plan(r)["ports"] if p["row"]["id"]==child["id"])
        self.assertEqual(c["tube"]["id"],100)
        self.assertAlmostEqual(c["outer"]["centre"][1],0,places=5)

    def test_automatic_branch_dependency(self):
        r,parent,child=branch_recipe();child["target"]="auto"
        c=next(p for p in core.plan(r)["ports"] if p["row"]["id"]==child["id"])
        self.assertIn(parent["id"],c["parents"])

    def test_cycles_and_missing_targets(self):
        r,parent,child=branch_recipe();parent["target"]=child["id"]
        with self.assertRaisesRegex(core.RecipeError,"Cyclic"):core.plan(r)
        parent["target"]="missing"
        with self.assertRaises(core.RecipeError):core.plan(r)

    def test_reference_outside_requires_manual(self):
        r=core.example_recipe();r["ports"]=r["ports"][:1]
        f=r["ports"][0];r["points"][0]["x"]=500
        # Keep base at a separate origin; reference point is outside its cavity.
        p=core.new_point("B");r["points"].append(p);r["bodies"][0]["point"]=p["id"]
        with self.assertRaises(core.RecipeError):core.plan(r)
        f.update(neck_mode="manual",neck_length=600)
        self.assertEqual(core.plan(r)["ports"][0]["length"],600)

    def test_row_build_closure_excludes_unbuilt_ports(self):
        r,parent,child=branch_recipe();extra=core.new_port(r["points"][0]["id"]);extra["elevation"]=90;r["ports"].append(extra)
        subset=core.build_subset(r,None,child["id"])
        self.assertEqual({f["id"] for f in subset["ports"]},{parent["id"],child["id"]})
        old=core.build_subset(r,None,extra["id"])
        subset=core.build_subset(r,old,child["id"])
        self.assertEqual(len(subset["ports"]),3)

    def test_imported_solid_manual_neck(self):
        r=core.new_recipe();p=r["points"][0]["id"]
        b=core.new_body(p,"existing");b.update(asset="shape.smt",wall=None);r["bodies"]=[b]
        f=core.new_port(p);f["neck_mode"]="manual";r["ports"]=[f]
        self.assertEqual(core.plan(r)["ports"][0]["length"],70)
        f["neck_mode"]="auto"
        with self.assertRaises(core.RecipeError):core.plan(r)
        r["ports"]=[];r["points"]=[]
        self.assertEqual(len(core.plan(r)["primitives"]),1)  # A placed snapshot needs no datum point.


class Exchange(unittest.TestCase):
    def test_portable_bundle_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);r=core.example_recipe()
            asset=folder/"input.smt";asset.write_bytes(b"mock geometry snapshot")
            b=core.new_body(r["points"][0]["id"],"existing");b.update(asset=str(asset),token="local-only");r["bodies"].append(b)
            bundle=folder/"chamber.zip";exchange.export_bundle(r,bundle)
            with zipfile.ZipFile(bundle) as z:
                self.assertTrue({"recipe.json","flanges.csv","bodies.csv","points.csv","report.md","defaults.json"}<=set(z.namelist()))
            loaded=exchange.import_recipe(bundle,folder/"assets")
            self.assertEqual(Path(loaded["bodies"][-1]["asset"]).read_bytes(),asset.read_bytes())
            self.assertNotIn("token",loaded["bodies"][-1]);self.assertEqual(loaded["ports"],r["ports"])

    def test_reject_bundle_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            r=core.example_recipe();r["bodies"][0]["asset"]="../outside.smt"
            p=Path(td)/"bad.zip"
            with zipfile.ZipFile(p,"w") as z:z.writestr("recipe.json",json.dumps(r));z.writestr("../outside.smt","bad")
            with self.assertRaisesRegex(core.RecipeError,"Invalid geometry asset"):exchange.import_recipe(p,Path(td)/"assets")
            self.assertFalse((Path(td)/"outside.smt").exists())

    def test_json_round_trip_and_report(self):
        with tempfile.TemporaryDirectory() as td:
            r=core.example_recipe();r["name"]="Chamber µ";r["ports"][0]["name"]="Pump | branch"
            p=Path(td)/"recipe.json";p.write_text(json.dumps(r),encoding="utf-8")
            self.assertEqual(exchange.import_recipe(p,Path(td)),core.normalize(r))
            self.assertIn("Pump \\| branch",exchange.report(r))


if __name__=="__main__":unittest.main()
