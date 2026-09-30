"""Regression tests for event ownership and API usage, without Fusion's kernel.

The fakes deliberately reject nested-native placement and dead renderer access.
They cannot verify native crash recovery, transactions, or solid geometry.
"""
import importlib
import json
import math
import tempfile
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from UHVChamberBuilder import core


class Document:
    def __init__(self,name):self.name=name;self.isValid=True


class Matrix:
    def __init__(self,values):self.values=list(values)
    def copy(self):return Matrix(self.values)
    def asArray(self):return list(self.values)


class DeadRenderer:
    def __getattribute__(self,name):raise AssertionError("Dead renderer was accessed: "+name)


class Collection:
    def __init__(self,values=()):self.values=list(values)
    @property
    def count(self):return len(self.values)
    def item(self,index):return self.values[index]


def component(name=""):
    return types.SimpleNamespace(name=name,tags={},occurrences=Occurrences(),bRepBodies=Collection(),constructionPoints=Collection(),constructionAxes=Collection())


class Occurrences(Collection):
    def addNewComponent(self,matrix):
        o=types.SimpleNamespace(component=component(),transform2=matrix,entityToken="test-occurrence")
        o.deleteMe=lambda:self.values.remove(o) is None
        o.createForAssemblyContext=Mock(return_value=types.SimpleNamespace(transform2=matrix,assemblyContext=True))
        self.values.append(o);return o


class FusionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adsk=types.ModuleType("adsk");adsk.core=types.ModuleType("adsk.core");adsk.fusion=types.ModuleType("adsk.fusion")
        for name in ["CustomEventHandler","HTMLEventHandler","CommandEventHandler","CommandCreatedEventHandler","UserInterfaceGeneralEventHandler","DocumentEventHandler"]:
            setattr(adsk.core,name,type(name,(),{}))
        adsk.core.DialogResults=types.SimpleNamespace(DialogYes=1,DialogNo=2)
        adsk.core.MessageBoxButtonTypes=types.SimpleNamespace(YesNoButtonType=1)
        adsk.core.MessageBoxIconTypes=types.SimpleNamespace(WarningIconType=1)
        adsk.fusion.Design=types.SimpleNamespace(cast=lambda obj:obj)
        adsk.fusion.DesignIntentTypes=types.SimpleNamespace(HybridDesignIntentType="hybrid")
        adsk.fusion.DesignTypes=types.SimpleNamespace(ParametricDesignType="parametric")
        adsk.core.Matrix3D=types.SimpleNamespace(create=lambda:Matrix([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]))
        adsk.core.Point3D=types.SimpleNamespace(create=lambda *xyz:xyz)
        adsk.fusion.CustomGraphicsSolidColorEffect=types.SimpleNamespace(cast=lambda value:value)
        adsk.fusion.CustomGraphicsBRepBody=types.SimpleNamespace(classType=lambda:"body")
        adsk.fusion.CustomGraphicsLines=types.SimpleNamespace(classType=lambda:"lines")
        adsk.doEvents=Mock()
        with patch.dict(sys.modules,{"adsk":adsk,"adsk.core":adsk.core,"adsk.fusion":adsk.fusion}):
            cls.backend=importlib.import_module("UHVChamberBuilder.fusion_backend")
            cls.entry=importlib.import_module("UHVChamberBuilder.UHVChamberBuilder")

    def setUp(self):
        m=self.entry
        for key,value in dict(_bound_document=None,_preview_document=None,_preview=None,_hidden=None,
                _doc_key="",_recipe=None,_busy=False,_pending=None,_messages=[],_handlers=[],_custom_id="test-idle",
                _flush_queued=False,_reload_pending=False,_stopping=False,_cancel_requested=False,
                _preview_serial=0,_operation_doc_key="",_progress_dialog=None).items():setattr(m,key,value)
        self.doc=Document("Current");self.design=types.SimpleNamespace(designIntent="single",activeOccurrence=None,rootComponent=types.SimpleNamespace(customGraphicsGroups=Collection()))
        self.palette=types.SimpleNamespace(isValid=True,isVisible=True,sendInfoToHTML=Mock())
        self.command=types.SimpleNamespace(execute=Mock(return_value=True))
        self.dialog=types.SimpleNamespace(isCancelButtonShown=False,show=Mock(),hide=Mock(),wasCancelled=False,message="")
        m._app=types.SimpleNamespace(activeDocument=self.doc,activeProduct=self.design,fireCustomEvent=Mock(return_value=True),activeViewport=types.SimpleNamespace(refresh=Mock()))
        m._ui=types.SimpleNamespace(palettes=types.SimpleNamespace(itemById=lambda _:self.palette),
                commandDefinitions=types.SimpleNamespace(itemById=lambda _:self.command),
                createProgressDialog=lambda:self.dialog,messageBox=Mock(return_value=1))
        m.bind_document()

    def html(self,action,**data):
        args=types.SimpleNamespace(action=action,data=json.dumps(data),returnData="")
        self.entry.HTMLHandler().notify(args)
        return json.loads(args.returnData)

    def test_repeated_activation_keeps_key_and_draft(self):
        m=self.entry;key=m._doc_key;draft={"unsaved":"retained"};m._recipe=draft
        m.Activated().notify(types.SimpleNamespace(document=self.doc))
        self.assertEqual(m._doc_key,key);self.assertIs(m._recipe,draft);self.assertFalse(m._messages)

    def test_switch_rejects_old_edits_and_background_close_does_not_rekey(self):
        m=self.entry;key=m._doc_key;new=Document("New Hybrid")
        m._app.activeDocument=new;m.Activated().notify(types.SimpleNamespace(document=new))
        new_key=m._doc_key
        with patch.object(self.backend,"save_recipe") as save:
            result=self.html("save",doc_key=key,recipe=core.example_recipe())
            self.assertEqual(result["code"],"document_changed");save.assert_not_called()
        self.doc.isValid=False;m.DocumentClosed().notify(types.SimpleNamespace(document=self.doc))
        self.assertEqual(m._doc_key,new_key)
        self.assertEqual([a for a,_ in m._messages],["reload"])

    def test_preview_cleanup_happens_before_document_destruction(self):
        m=self.entry;group=types.SimpleNamespace(isValid=True,deleteMe=Mock())
        hidden=types.SimpleNamespace(isValid=True,isLightBulbOn=False)
        m._preview=group;m._preview_document=self.doc;m._hidden=(hidden,True)
        m.LeavingDocument().notify(types.SimpleNamespace(document=self.doc))
        group.deleteMe.assert_called_once();self.assertTrue(hidden.isLightBulbOn)
        self.doc.isValid=False;m.DocumentClosed().notify(types.SimpleNamespace(document=self.doc))
        group.deleteMe.assert_called_once();self.assertIsNone(m._preview)

    def test_dead_renderer_handles_are_dropped_without_access(self):
        m=self.entry;self.doc.isValid=False
        m._preview_document=self.doc;m._preview=DeadRenderer();m._hidden=(DeadRenderer(),True)
        m.clear_preview()
        self.assertIsNone(m._preview);self.assertIsNone(m._hidden)

    def test_close_defers_cleanup_and_does_not_clear_a_new_preview(self):
        m=self.entry;old=types.SimpleNamespace(isValid=True,deleteMe=Mock())
        m._preview=old;m._preview_document=self.doc
        m.Closed().notify(None)
        old.deleteMe.assert_not_called();self.palette.sendInfoToHTML.assert_not_called()
        m.clear_preview()
        new=types.SimpleNamespace(isValid=True,deleteMe=Mock());m._preview=new;m._preview_document=self.doc
        m.FlushMessages().notify(None);new.deleteMe.assert_not_called()
        m.Closed().notify(None);m.FlushMessages().notify(None);new.deleteMe.assert_called_once()

    def test_busy_bootstrap_refreshes_after_command_finishes(self):
        m=self.entry;m._busy=True
        self.assertEqual(self.html("bootstrap")["code"],"busy");self.assertTrue(m._reload_pending)
        m.OpenDestroyed({}).notify(None);self.assertTrue(m._busy)
        m.Destroyed({"key":m._doc_key,"result":{"message":"Done"}}).notify(None)
        self.assertFalse(m._busy);self.palette.sendInfoToHTML.assert_not_called()
        m.FlushMessages().notify(None)
        self.assertEqual(self.palette.sendInfoToHTML.call_args.args[0],"reload")
        self.assertFalse(m._reload_pending)

    def test_preview_is_queued_as_a_native_command(self):
        m=self.entry
        with patch.object(self.backend,"save_recipe"),patch.object(self.backend,"prepare") as prepare:
            result=self.html("preview",doc_key=m._doc_key,recipe=core.example_recipe())
        self.assertTrue(result["result"]["queued"]);self.assertTrue(m._busy)
        self.command.execute.assert_called_once();prepare.assert_not_called()
        self.assertEqual(m._pending["action"],"preview")

    def build(self,answer=1,switch_during_warning=False):
        m=self.entry;recipe=core.example_recipe();scope={}
        m._pending=dict(action="build",doc_key=m._doc_key,recipe=recipe)
        def warning(*args):
            if switch_during_warning:m._app.activeDocument=Document("Other")
            return answer
        m._ui.messageBox.side_effect=warning
        with patch.object(self.backend,"committed_recipe",return_value=None),\
             patch.object(self.backend,"prepare",return_value=dict(plan={"recipe":recipe},entries={},diagnostics=[])),\
             patch.object(self.backend,"commit",return_value={}) as commit,patch.object(m,"log",return_value="test.log"):
            args=types.SimpleNamespace(executeFailed=False);m.Execute(scope).notify(args)
        return scope,commit,args

    def test_build_confirms_conversion_in_the_same_document(self):
        scope,commit,args=self.build()
        self.assertFalse(args.executeFailed);self.assertIn("Build complete",scope["result"]["message"])
        self.assertIs(commit.call_args.args[1],self.design)
        self.assertTrue(commit.call_args.kwargs["convert_to_hybrid"])
        self.assertIs(self.entry._app.activeDocument,self.doc)

    def test_declining_conversion_does_not_commit(self):
        scope,commit,args=self.build(answer=2)
        commit.assert_not_called();self.assertFalse(args.executeFailed)
        self.assertEqual(self.design.designIntent,"single");self.assertIn("cancelled",scope["result"]["message"])

    def test_context_is_checked_again_after_conversion_warning(self):
        _,commit,args=self.build(switch_during_warning=True)
        self.assertTrue(args.executeFailed);commit.assert_not_called()

    def test_commit_requires_consent_before_changing_design_intent(self):
        with self.assertRaisesRegex(core.RecipeError,"confirmation"):
            self.backend.commit(self.entry._app,self.design,{},core.new_recipe())
        self.assertEqual(self.design.designIntent,"single")

    def test_saved_old_angle_preference_is_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder)
            (cache/"defaults.json").write_text(json.dumps(dict(flange_angle_mode="azimuth_elevation",gap=15)))
            with patch.object(self.entry,"CACHE",cache):defaults=self.entry.app_defaults()
        self.assertNotIn("flange_angle_mode",defaults)
        self.assertEqual(defaults["gap"],15)

    def test_citation_copy_is_independent_of_document_and_build_state(self):
        m=self.entry;m._busy=True;m._app.activeDocument=None;self.doc.isValid=False
        original=m._recipe
        with patch.object(m.clipboard_support,"copy_text") as copy,patch.object(self.backend,"save_recipe") as save:
            result=self.html("copy_text",text="Amon P. Lanz (2026). UHV Chamber Builder.",recipe={"invalid":"draft"})
        self.assertTrue(result["result"]["copied"])
        copy.assert_called_once_with("Amon P. Lanz (2026). UHV Chamber Builder.")
        save.assert_not_called();self.assertIs(m._recipe,original);self.assertTrue(m._busy)

    def test_citation_clipboard_failure_returns_manual_copy_fallback(self):
        with patch.object(self.entry.clipboard_support,"copy_text",side_effect=RuntimeError("Clipboard busy")):
            result=self.html("copy_text",text="Citation")
        self.assertTrue(result["ok"]);self.assertFalse(result["result"]["copied"])
        self.assertEqual(result["result"]["message"],"Clipboard busy")

    def placement(self,at_parent):
        values=[0,-1,0,12,1,0,0,23,0,0,1,34,0,0,0,1]
        chamber=types.SimpleNamespace(transform2=Matrix(values))
        proxy=types.SimpleNamespace(assemblyContext=chamber,transform2=Matrix(values if at_parent else [0]*16),isGroundToParent=True)
        class NestedNative:
            def createForAssemblyContext(self,parent):
                if parent is not chamber:raise AssertionError("Wrong assembly context")
                return proxy
            @property
            def transform2(self):raise AssertionError("Native transform must not be accessed")
            @transform2.setter
            def transform2(self,value):raise AssertionError("Native transform must not be assigned")
        return NestedNative(),chamber,proxy

    def test_correct_nested_placement_needs_no_override(self):
        child,chamber,proxy=self.placement(True);original=proxy.transform2
        self.assertFalse(self.backend.place_child_at_chamber(child,chamber))
        self.assertIs(proxy.transform2,original);self.assertTrue(proxy.isGroundToParent)

    def test_moved_child_uses_parent_world_pose_on_root_proxy(self):
        child,chamber,proxy=self.placement(False)
        self.assertTrue(self.backend.place_child_at_chamber(child,chamber))
        self.assertEqual(proxy.transform2.asArray(),chamber.transform2.asArray())
        self.assertFalse(proxy.isGroundToParent)

    def graphics_group(self,ident="",name="",rgb=(0,140,245)):
        def entity(kind,color):
            return types.SimpleNamespace(objectType=kind,weight=2,color=types.SimpleNamespace(color=types.SimpleNamespace(red=color[0],green=color[1],blue=color[2])))
        group=Collection([entity("body",(174,184,195)),entity("lines",rgb)])
        group.id=ident;group.name=name;group.isValid=True
        collection=self.design.rootComponent.customGraphicsGroups
        group.deleteMe=Mock(side_effect=lambda:collection.values.remove(group) is None)
        collection.values.append(group);return group

    def test_cleanup_recovers_old_and_tagged_previews_only(self):
        old=self.graphics_group();current=self.graphics_group(self.backend.PREVIEW_ID+"chamber","UHV chamber preview")
        other=self.graphics_group("OtherAddin","Other graphics")
        unrelated=self.graphics_group(rgb=(100,20,30))
        named=self.graphics_group(name="User graphics")
        self.assertEqual(self.backend.clear_preview_graphics(self.design,True),2)
        old.deleteMe.assert_called_once();current.deleteMe.assert_called_once()
        for keep in [other,unrelated,named]:keep.deleteMe.assert_not_called()

    def test_cleanup_failure_is_reported(self):
        group=self.graphics_group(self.backend.PREVIEW_ID+"chamber")
        group.deleteMe=Mock(return_value=False)
        with self.assertRaisesRegex(core.RecipeError,"could not remove"):self.backend.clear_preview_graphics(self.design)

    def test_save_clears_preview_and_restores_built_visibility(self):
        m=self.entry;group=self.graphics_group(self.backend.PREVIEW_ID+"chamber")
        hidden=types.SimpleNamespace(isValid=True,isLightBulbOn=False)
        m._preview=group;m._preview_document=self.doc;m._hidden=(hidden,True)
        m.SavingDocument().notify(types.SimpleNamespace(document=self.doc))
        self.assertTrue(hidden.isLightBulbOn);self.assertEqual(self.design.rootComponent.customGraphicsGroups.count,0)
        self.assertIsNone(m._preview)

    def test_clear_preview_command_recovers_groups_without_python_handle(self):
        m=self.entry;group=self.graphics_group();m._pending=dict(action="clear_preview",doc_key=m._doc_key)
        args=types.SimpleNamespace(executeFailed=False);scope={};m.Execute(scope).notify(args)
        self.assertFalse(args.executeFailed);group.deleteMe.assert_called_once()
        self.assertIn("earlier versions",scope["result"]["message"])

    def test_clear_preview_does_not_require_a_valid_draft(self):
        with patch.object(self.backend,"save_recipe") as save:
            result=self.html("clear_preview",doc_key=self.entry._doc_key,recipe={"invalid":"draft"})
        self.assertTrue(result["result"]["queued"]);save.assert_not_called()

    def test_cylinder_endpoints_preserve_actual_azimuth_and_elevation(self):
        manager=types.SimpleNamespace(createCylinderOrCone=Mock(return_value=object()))
        for az in [-75,-45,-15,15,45,75]:
            for el in [0,30,-30,90]:
                origin=(7,11,13);normal=core.frame(az,el)[2]
                with patch.object(self.backend,"manager",return_value=manager):self.backend.cyl(origin,normal,-3,17,5)
                a,ra,b,rb=manager.createCylinderOrCone.call_args.args
                direction=core.unit(core.sub(b,a))
                for x,y in zip(direction,normal):self.assertAlmostEqual(x,y)
                self.assertAlmostEqual(core.norm(core.sub(b,a)),2)  # 20 mm in Fusion cm.
                self.assertEqual((ra,rb),(.5,.5))

    def test_gasket_solid_spans_offset_minus_thickness_to_offset(self):
        r=core.example_recipe();r["defaults"].update(gasket_features=True,gasket_standoff=.5)
        port=core.plan(r)["ports"][0];calls=[]
        def cylinder(c,n,lo,hi,radius):
            body=types.SimpleNamespace(lo=lo,hi=hi,radius=radius,normal=n,centre=c);calls.append(body);return body
        manager=types.SimpleNamespace(createCylinderOrCone=Mock(return_value=object()))
        with patch.object(self.backend,"manager",return_value=manager),patch.object(self.backend,"cyl",side_effect=cylinder),patch.object(self.backend,"boolean"):
            bodies=self.backend.flange_bodies(port,r["defaults"])
        gasket=next(b for _,b,kind in bodies if kind=="gasket")
        self.assertAlmostEqual(gasket.hi,.5)
        self.assertAlmostEqual(gasket.lo,.5-port["dims"]["gasket_t"])
        self.assertNotIn(gasket,[b for _,b,kind in bodies if kind=="flange"])

    def test_x_ring_complete_flange_cylinder_arguments_rotate_about_x(self):
        """Check actual solid/bore/bolt coordinates, including the signed-tilt seam."""
        source=Path(__file__).resolve().parents[1]/"examples"/"X_axis_ring.json"
        ca,sa=math.cos(math.pi/6),math.sin(math.pi/6)
        def rx(p):return (p[0],ca*p[1]-sa*p[2],sa*p[1]+ca*p[2])
        for config in ["inline","straddled","rotatable"]:
            for bolts in [5,6]:  # An odd count exposes a hidden 180-degree clocking flip.
                with self.subTest(configuration=config,bolts=bolts):
                    r=json.loads(source.read_text());r["defaults"]["gasket_features"]=True
                    for f in r["ports"]:
                        if not f.get("endpoint"):
                            f.update(configuration=config,roll=23.5,deviate=True,overrides={"bolts":bolts})
                    ports=[p for p in core.plan(r)["ports"] if not p["row"].get("endpoint")]
                    ports.sort(key=lambda p:(p["row"]["elevation"] if p["row"]["azimuth"]>=0 else 180-p["row"]["elevation"])%360)
                    cylinders=[]
                    for p in ports:
                        manager=types.SimpleNamespace(createCylinderOrCone=Mock(side_effect=lambda *args:object()),copy=Mock(return_value=object()))
                        with patch.object(self.backend,"manager",return_value=manager),patch.object(self.backend,"boolean"):
                            self.backend.flange_bodies(p,r["defaults"])
                        cylinders.append([call.args for call in manager.createCylinderOrCone.call_args_list])
                    self.assertEqual(len(cylinders),12)
                    self.assertEqual(len(cylinders[0]),bolts+7+(config=="rotatable"))
                    for prev,nxt in zip(cylinders,cylinders[1:]+cylinders[:1]):
                        self.assertEqual(len(prev),len(nxt))
                        for (a,ra,b,rb),(c,rc,d,rd) in zip(prev,nxt):
                            self.assertEqual((ra,rb),(rc,rd))
                            for actual,expected in [(c,rx(a)),(d,rx(b))]:
                                for x,y in zip(actual,expected):self.assertAlmostEqual(x,y,places=10)

    def test_gasket_component_migration_and_disable(self):
        backend=self.backend;r=core.new_recipe();r["points"]=[]
        f=core.new_port("p");f["number"]="1";r["ports"]=[f];r["defaults"]["gasket_features"]=True
        root=component();design=types.SimpleNamespace(rootComponent=root,activeOccurrence=None,designIntent="hybrid",designType="direct",tags={})
        chamber=root.occurrences.addNewComponent(backend.adsk.core.Matrix3D.create());chamber.component.tags["chamber_id"]=r["id"]
        flange=chamber.component.occurrences.addNewComponent(backend.adsk.core.Matrix3D.create());flange.component.tags["row_id"]=f["id"]
        flange.component.bRepBodies.values=[types.SimpleNamespace(tags={"kind":"flange"}),types.SimpleNamespace(tags={"kind":"gasket"})]
        entry=dict(name="Port",signature="new-layout",bodies=[("Flange",object(),"flange")],gasket_bodies=[("Nominal gasket",object(),"gasket")])
        prepared=dict(plan=dict(recipe=r,ports=[]),entries={f["id"]:entry},diagnostics=[])
        def add_bodies(app,d,comp,bodies):comp.bRepBodies.values.extend(types.SimpleNamespace(tags={"kind":kind}) for _,_,kind in bodies)
        with patch.object(backend,"attr",side_effect=lambda o,k:o.tags.get(k)),patch.object(backend,"tag",side_effect=lambda o,k,v:o.tags.update({k:str(v)})),\
             patch.object(backend,"clear_managed_geometry",side_effect=lambda c:c.bRepBodies.values.clear()),patch.object(backend,"add_bodies",side_effect=add_bodies),\
             patch.object(backend,"make_datums"),patch.object(backend,"place_child_at_chamber",return_value=False) as placement:
            result=backend.commit(self.entry._app,design,prepared,r)
            self.assertEqual(flange.component.bRepBodies.count,1)
            self.assertEqual(flange.component.occurrences.count,1)
            gasket=flange.component.occurrences.item(0)
            self.assertEqual(gasket.component.bRepBodies.item(0).tags["kind"],"gasket")
            self.assertIs(placement.call_args.args[1],flange.createForAssemblyContext.return_value)
            self.assertEqual(result["statuses"][f["id"]],"Up to date")
            self.assertEqual(result["inventory"],[])
            self.assertFalse(backend.has_manual_content(flange.component))
            gasket.component.bRepBodies.values.append(types.SimpleNamespace(tags={}))
            with self.assertRaisesRegex(core.RecipeError,"manual geometry"):
                backend.sync_gasket(self.entry._app,design,flange,chamber,dict(entry,gasket_bodies=[]))
            gasket.component.bRepBodies.values.pop()
            backend.sync_gasket(self.entry._app,design,flange,chamber,dict(entry,gasket_bodies=[]))
            self.assertEqual(flange.component.occurrences.count,0)


if __name__=="__main__":unittest.main()
