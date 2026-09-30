"""Fusion add-in entry point. Extract this entire directory before registering."""
from pathlib import Path
import datetime
import json
import tempfile
import traceback
import uuid
import time
import adsk.core
import adsk.fusion
from . import core, fusion_backend as backend, exchange, clipboard_support

PREFIX="UHVChamberBuilder"
OPEN=PREFIX+"Open";EXEC=PREFIX+"Execute";PALETTE=PREFIX+"Palette"
_app=None;_ui=None;_handlers=[];_preview=None;_pending=None;_busy=False
_doc_key="";_recipe=None;_hidden=None;_progress_dialog=None;_operation_doc_key=""
_bound_document=None;_preview_document=None;_preview_serial=0
_messages=[];_custom_id="";_flush_queued=False;_reload_pending=False
_stopping=False;_cancel_requested=False;_last_pump=0.0
CACHE=Path.home()/".uhv_chamber_builder"


def log(message):
    path=Path(tempfile.gettempdir())/"UHVChamberBuilder.log"
    try:
        if path.exists() and path.stat().st_size>2_000_000:path.write_text("",encoding="utf-8")
        with path.open("a",encoding="utf-8") as f:f.write(datetime.datetime.now().isoformat()+" ["+core.VERSION+"] "+message+"\n")
    except OSError:pass
    return str(path)


def listen(event,handler,scope=None):
    handler.scope=scope;event.add(handler);_handlers.append((event,handler))


def release(scope):
    for event,handler in list(_handlers):
        if handler.scope is scope:
            try:event.remove(handler)
            except Exception:pass
            _handlers.remove((event,handler))


def design():
    d=adsk.fusion.Design.cast(_app.activeProduct)
    if not d:raise core.RecipeError("Open a Fusion design in the Design workspace.")
    return d


def palette():
    try:return _ui.palettes.itemById(PALETTE) if _ui else None
    except RuntimeError:return None


def same_document(a,b):
    try:return a is not None and b is not None and a==b
    except RuntimeError:return False


def live_document(doc):
    try:return doc is not None and doc.isValid
    except RuntimeError:return False


def bind_document():
    """Ignore repeated activation of the same document; only real switches rekey."""
    global _bound_document,_doc_key,_recipe
    current=_app.activeDocument
    if not live_document(current):current=None
    if same_document(current,_bound_document) or (current is None and _bound_document is None):return False
    _bound_document=current;_doc_key=str(uuid.uuid4()) if current else "";_recipe=None
    return True


def send(action,data,key=None):
    """Never enter the HTML bridge from a document/command/close callback."""
    global _flush_queued,_reload_pending
    if _stopping:return
    if action=="reload":
        _reload_pending=True
        if _busy:return
    key=_doc_key if key is None else key
    # Keep progress and reload notifications bounded while the kernel is busy.
    if action in ("progress","reload"):
        _messages[:]=[(a,d) for a,d in _messages if a!=action]
    _messages.append((action,dict(data,doc_key=key)))
    if not _flush_queued and _custom_id:
        _flush_queued=True
        try:
            if not _app.fireCustomEvent(_custom_id):_flush_queued=False
        except RuntimeError:_flush_queued=False


def clear_preview():
    global _preview,_hidden,_preview_document,_preview_serial
    group,hidden,owner=_preview,_hidden,_preview_document
    _preview=None;_hidden=None;_preview_document=None;_preview_serial+=1
    # A closed document's renderer objects must never be queried, even isValid.
    if not live_document(owner):return
    if group:
        try:
            if group.isValid:group.deleteMe()
        except Exception:pass
    if hidden:
        try:
            if hidden[0].isValid:hidden[0].isLightBulbOn=hidden[1]
        except Exception:pass


class FlushMessages(adsk.core.CustomEventHandler):
    def notify(self,args):
        global _flush_queued,_reload_pending
        _flush_queued=False
        messages=list(_messages);_messages.clear()
        for action,data in messages:
            if _stopping:return
            if action=="clear_after_close":
                if data.get("preview_serial")==_preview_serial:clear_preview()
                continue
            if action=="reload":
                if _busy:_reload_pending=True;continue
                bind_document();data["doc_key"]=_doc_key;_reload_pending=False
            elif data.get("doc_key")!=_doc_key:continue
            p=palette()
            try:
                if p and p.isValid and p.isVisible:p.sendInfoToHTML(action,json.dumps(data,allow_nan=False))
            except RuntimeError:pass  # The palette may have closed before delivery.


def bootstrap():
    global _recipe
    bind_document()
    if not live_document(_bound_document):
        return dict(available=False,doc_key="",document="No open design",version=core.VERSION,message="Open a Fusion design to edit a chamber.")
    d=adsk.fusion.Design.cast(_app.activeProduct)
    if not d:return dict(available=False,doc_key=_doc_key,document=_bound_document.name,version=core.VERSION,message="Switch to the Fusion Design workspace.")
    _recipe=backend.load_recipe(d)
    if not backend.attr(d,"draft") and not backend.saved_chambers(d):_recipe["defaults"]=app_defaults()
    return dict(available=True,recipe=_recipe,catalog=core.CATALOG,version=core.VERSION,doc_key=_doc_key,
                document=_app.activeDocument.name,**backend.state(d,_recipe))


def begin_progress(title):
    global _progress_dialog,_operation_doc_key,_cancel_requested,_last_pump
    _operation_doc_key=_doc_key
    _cancel_requested=False;_last_pump=0
    _progress_dialog=_ui.createProgressDialog()
    _progress_dialog.isCancelButtonShown=True
    _progress_dialog.show(title,"Preparing geometry…",0,100,0)


def end_progress():
    global _progress_dialog
    if _progress_dialog:
        dialog=_progress_dialog;_progress_dialog=None
        try:dialog.hide()
        except RuntimeError:pass


def progress(message):
    global _last_pump
    if _cancel_requested or not live_document(_bound_document) or (_operation_doc_key and _operation_doc_key!=_doc_key):
        raise core.RecipeError("Document changed during geometry preparation; operation cancelled.")
    if _progress_dialog:
        if _progress_dialog.wasCancelled:raise core.RecipeError("Operation cancelled. Previous built geometry is retained.")
        _progress_dialog.message=message
    send("progress",dict(message=message))
    if time.monotonic()-_last_pump>=0.1:
        _last_pump=time.monotonic();adsk.doEvents()
    if _cancel_requested or not live_document(_bound_document) or (_operation_doc_key and _operation_doc_key!=_doc_key):
        raise core.RecipeError("Document changed during geometry preparation; operation cancelled.")


def app_defaults():
    path=CACHE/"defaults.json"
    if path.is_file():
        try:
            defaults=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(defaults,dict):
                defaults.pop("flange_angle_mode",None)
                return defaults
        except (OSError,ValueError):pass
    return core.default_settings()


def pick_source(row_id,cavity=False):
    global _recipe
    p=palette();p.isVisible=False;key=_doc_key
    try:
        try:sel=_ui.selectEntity("Select a solid body (or a single-body component)","SolidBodies,Occurrences")
        except RuntimeError:return dict(cancelled=True)
        if key!=_doc_key:raise core.RecipeError("Document changed during selection. Select the solid again in the intended document.")
        body=adsk.fusion.BRepBody.cast(sel.entity)
        if not body:
            occ=adsk.fusion.Occurrence.cast(sel.entity)
            if not occ or occ.component.bRepBodies.count!=1:raise core.RecipeError("Select the specific solid body inside this component.")
            body=occ.component.bRepBodies.item(0).createForAssemblyContext(occ)
        row=next(x for x in _recipe["bodies"] if x["id"]==row_id)
        # Snapshot the selected body's placement in the chamber coordinate frame.
        copied=backend.source_body(design(),dict(id=row_id,name=row["name"],token=body.entityToken))
        chamber=backend.find_chamber(design(),_recipe["id"])
        if chamber:
            inv=chamber.transform2.copy()
            if not inv.invert() or not backend.manager().transform(copied,inv):raise core.RecipeError("Cannot transform selected body into chamber coordinates.")
        folder=CACHE/"assets";folder.mkdir(parents=True,exist_ok=True);path=folder/(core.uid("solid")+".smt")
        if not backend.manager().exportToFile([copied],str(path)):raise core.RecipeError("Could not save the selected body snapshot.")
        row["cavity_asset" if cavity else "asset"]=str(path)
        row["cavity_token" if cavity else "token"]=body.entityToken
        row["source_name" if not cavity else "cavity_name"]=body.name
        backend.save_recipe(design(),_recipe)
        return dict(recipe=_recipe)
    finally:p.isVisible=True


def file_exchange(action):
    global _recipe
    dialog=_ui.createFileDialog();dialog.isMultiSelectEnabled=False
    dialog.title="Import UHV recipe" if action=="import" else "Export UHV chamber"
    suffix={"export_json":"json","export_bundle":"zip","export_report":"md"}.get(action,"json")
    dialog.filter="UHV recipes (*.json;*.zip)" if action=="import" else suffix.upper()+" files (*."+suffix+")"
    dialog.initialFilename="UHV_chamber."+suffix
    result=dialog.showOpen() if action=="import" else dialog.showSave()
    if result!=adsk.core.DialogResults.DialogOK:return dict(cancelled=True)
    path=Path(dialog.filename)
    if action=="import":
        r=exchange.import_recipe(path,CACHE/"assets")
        # Import starts an independent recipe; an existing chamber isn't overwritten.
        r["id"]=core.uid("chamber");_recipe=r;backend.save_recipe(design(),r)
        return dict(recipe=r,**backend.state(design(),r))
    if path.suffix.lower()!="."+suffix:path=path.with_suffix("."+suffix)
    if action=="export_bundle":exchange.export_bundle(_recipe,path)
    elif action=="export_report":path.write_text(exchange.report(_recipe),encoding="utf-8")
    else:path.write_text(json.dumps(_recipe,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    return dict(message="Saved "+str(path))


class HTMLHandler(adsk.core.HTMLEventHandler):
    def notify(self,args):
        global _recipe,_pending,_busy,_reload_pending
        try:
            action=args.action;data=json.loads(args.data or "{}")
            if action=="copy_text":
                # Citation copying is independent of a design or build transaction.
                try:
                    clipboard_support.copy_text(data.get("text",""));result=dict(copied=True)
                except Exception as exc:result=dict(copied=False,message=str(exc))
                args.returnData=json.dumps(dict(ok=True,result=result));return
            if _busy:
                if action=="bootstrap":_reload_pending=True
                args.returnData=json.dumps(dict(ok=False,code="busy",error="Wait for the current operation to finish."));return
            bind_document()
            if action!="bootstrap" and (not live_document(_bound_document) or data.get("doc_key")!=_doc_key):
                args.returnData=json.dumps(dict(ok=False,code="document_changed",error="Refreshing the active document."));return
            if action=="bootstrap":result=bootstrap()
            else:
                if action in ("section","new_hybrid"):raise core.RecipeError("This control was removed in V1.0.2. Stop and restart the updated add-in.")
                if "recipe" in data and action!="clear_preview":
                    _recipe=core.normalize(data["recipe"])
                    if action not in ("validate","save"):backend.save_recipe(design(),_recipe)
                if action=="validate":
                    checked=core.validate(_recipe);_recipe=checked["recipe"]
                    result=dict(errors=checked["errors"],resolved=checked["resolved"],**backend.state(design(),_recipe))
                elif action=="save":backend.save_recipe(design(),_recipe);result={}
                elif action=="save-app-defaults":
                    CACHE.mkdir(parents=True,exist_ok=True);(CACHE/"defaults.json").write_text(json.dumps(_recipe["defaults"],indent=2,allow_nan=False),encoding="utf-8");result=dict(message="Defaults saved for new chambers.")
                elif action in ("preview","build","clear_preview","delete_geometry"):
                    _pending=dict(action=action,doc_key=_doc_key,recipe=_recipe,**{k:v for k,v in data.items() if k not in ("recipe","doc_key")})
                    _busy=True
                    try:
                        if not _ui.commandDefinitions.itemById(EXEC).execute():raise core.RecipeError("Fusion could not start the update command. Finish the active command and retry.")
                    except Exception:_pending=None;_busy=False;raise
                    result=dict(queued=True)
                elif action=="pick_source":
                    _busy=True
                    try:result=pick_source(data["row"],data.get("cavity",False))
                    finally:
                        _busy=False
                        if _reload_pending or data.get("doc_key")!=_doc_key:send("reload",{})
                elif action in ("import","export_json","export_bundle","export_report"):result=file_exchange(action)
                elif action=="highlight":backend.select_entity(design(),data["token"]);result={}
                elif action=="refresh":result=backend.state(design(),_recipe)
                elif action=="load":_recipe=backend.load_recipe(design(),data["id"]);result=dict(recipe=_recipe,**backend.state(design(),_recipe))
                elif action in ("new","example"):
                    clear_preview();_recipe=core.example_recipe() if action=="example" else core.new_recipe()
                    if action=="new":_recipe["defaults"]=app_defaults()
                    backend.save_recipe(design(),_recipe)
                    result=dict(recipe=_recipe,**backend.state(design(),_recipe))
                else:raise core.RecipeError("Unknown command: "+action)
            args.returnData=json.dumps(dict(ok=True,result=dict(result,doc_key=_doc_key)),allow_nan=False)
        except Exception as exc:
            path=log(traceback.format_exc())
            args.returnData=json.dumps(dict(ok=False,error=str(exc),row=getattr(exc,"row_id",""),log=path))


class Execute(adsk.core.CommandEventHandler):
    def __init__(self,scope):super().__init__();self.context=scope
    def notify(self,args):
        global _pending,_recipe,_preview,_preview_document,_hidden
        request=_pending;_pending=None
        self.context["key"]=request.get("doc_key",_doc_key) if request else _doc_key
        try:
            if not request or request["doc_key"]!=_doc_key:raise core.RecipeError("Document changed before the command started.")
            action=request["action"];clear_preview();d=design()
            backend.clear_preview_graphics(d,include_legacy=True)
            _app.activeViewport.refresh()
            if action in ("preview","build"):
                draft=request["recipe"]
                subset=core.build_subset(draft,backend.committed_recipe(d,draft["id"]),request.get("row"))
                if action=="build":core.require_flange_numbers(subset)
                begin_progress("Preview UHV chamber" if action=="preview" else "Build UHV chamber")
                try:
                    prepared=backend.prepare(d,subset,progress)
                    progress("Finishing chamber geometry")
                finally:end_progress()
                if _cancel_requested or request["doc_key"]!=_doc_key or not live_document(_bound_document) or not same_document(_bound_document,_app.activeDocument):raise core.RecipeError("Document changed or operation cancelled before committing geometry.")
                self.context["prepared"]=prepared
                if action=="preview":
                    _preview=backend.preview(d,prepared,request.get("row"));_preview_document=_bound_document
                    occ=backend.find_chamber(d,draft["id"])
                    if occ:_hidden=(occ,occ.isLightBulbOn);occ.isLightBulbOn=False
                    result=dict(diagnostics=prepared["diagnostics"],message="Preview ready. Clear preview to return to built geometry.")
                else:
                    convert=not backend.build_context(d)["allowed"]
                    if convert:
                        reply=_ui.messageBox("This chamber needs internal components. Switch the current document to Hybrid and build?\n\nThis changes the current document's design type; no new document is created.","Switch to Hybrid",adsk.core.MessageBoxButtonTypes.YesNoButtonType,adsk.core.MessageBoxIconTypes.WarningIconType)
                        if reply!=adsk.core.DialogResults.DialogYes:
                            self.context["result"]=dict(message="Build cancelled. Document type is unchanged.");return
                    if _cancel_requested or request["doc_key"]!=_doc_key or not same_document(_bound_document,_app.activeDocument):raise core.RecipeError("Document changed or operation cancelled before committing geometry.")
                    result=backend.commit(_app,d,prepared,draft,convert_to_hybrid=convert)
                    result.update(diagnostics=prepared["diagnostics"],message="Build complete. Save the Fusion document to retain the chamber and recipe.")
            elif action=="clear_preview":
                result=dict(message="Preview cleared, including recognized leftovers from earlier versions.")
            elif action=="delete_geometry":
                entity=backend.select_entity(design(),request["token"])
                if not (adsk.fusion.BRepBody.cast(entity) or adsk.fusion.Occurrence.cast(entity)):raise core.RecipeError("Only selected bodies/occurrences can be removed here.")
                entity.deleteMe();result=backend.state(design(),_recipe)
            self.context["result"]=result
        except Exception as exc:
            if request and request.get("action")=="preview":clear_preview()
            args.executeFailed=True
            self.context["error"]=dict(message=str(exc),row=getattr(exc,"row_id",""),log=log(traceback.format_exc()))


class Destroyed(adsk.core.CommandEventHandler):
    def __init__(self,scope):super().__init__();self.context=scope
    def notify(self,args):
        global _busy
        _busy=False
        if _reload_pending or self.context.get("key")!=_doc_key:send("reload",{})
        elif self.context.get("key")==_doc_key:
            if "error" in self.context:send("failed",self.context["error"])
            elif "result" in self.context:send("completed",self.context["result"])
        release(self.context);self.context.clear()


class ExecuteCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self,args):
        global _busy
        _busy=True;scope={};args.command.isAutoExecute=True
        listen(args.command.execute,Execute(scope),scope);listen(args.command.destroy,Destroyed(scope),scope)


class Closed(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self,args):
        global _cancel_requested
        if _busy:_cancel_requested=True
        send("clear_after_close",dict(preview_serial=_preview_serial))


def show():
    if _busy:return
    design();bind_document();p=palette()
    if not p:
        url=(Path(__file__).resolve().parent/"ui"/"index.html").as_uri()+"?v="+core.VERSION
        p=_ui.palettes.add(PALETTE,"UHV Chamber Builder",url,True,True,True,1280,880,True)
        listen(p.incomingFromHTML,HTMLHandler());listen(p.closed,Closed())
    else:p.isVisible=True;send("reload",{})


class OpenExecute(adsk.core.CommandEventHandler):
    def notify(self,args):
        try:show()
        except Exception as exc:_ui.messageBox(str(exc),"UHV Chamber Builder")


class OpenCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self,args):
        scope={};listen(args.command.execute,OpenExecute(),scope);listen(args.command.destroy,OpenDestroyed(scope),scope)


class OpenDestroyed(adsk.core.CommandEventHandler):
    def __init__(self,scope):super().__init__();self.context=scope
    def notify(self,args):release(self.context)


class Activated(adsk.core.DocumentEventHandler):
    def notify(self,args):
        if bind_document():send("reload",{})


class LeavingDocument(adsk.core.DocumentEventHandler):
    def notify(self,args):
        global _cancel_requested
        if _busy and same_document(args.document,_bound_document):_cancel_requested=True
        if same_document(args.document,_preview_document):clear_preview()


class DocumentClosed(adsk.core.DocumentEventHandler):
    def notify(self,args):
        # Never dereference renderer handles after document destruction.
        if not live_document(_preview_document):clear_preview()
        if not live_document(_bound_document):send("reload",{})


class SavingDocument(adsk.core.DocumentEventHandler):
    def notify(self,args):
        # Preview graphics and their temporary visibility changes must never
        # be part of the document the user saves.
        try:
            if same_document(args.document,_preview_document):clear_preview()
            if same_document(args.document,_app.activeDocument):
                d=adsk.fusion.Design.cast(_app.activeProduct)
                if d:backend.clear_preview_graphics(d,include_legacy=True)
        except Exception:log("Preview cleanup before save:\n"+traceback.format_exc())


def run(context):
    global _app,_ui,_custom_id,_stopping
    _app=adsk.core.Application.get();_ui=_app.userInterface;_stopping=False;bind_document()
    try:
        _custom_id=PREFIX+"IdleUI_"+uuid.uuid4().hex
        listen(_app.registerCustomEvent(_custom_id),FlushMessages())
        for ident,title,handler in [(OPEN,"UHV Chamber Builder",OpenCreated()),(EXEC,"Update UHV chamber",ExecuteCreated())]:
            definition=_ui.commandDefinitions.itemById(ident)
            if definition:definition.deleteMe()
            definition=_ui.commandDefinitions.addButtonDefinition(ident,title,"Table-driven UHV chamber visualization")
            listen(definition.commandCreated,handler)
        panel=_ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
        if panel and not panel.controls.itemById(OPEN):
            panel.controls.addCommand(_ui.commandDefinitions.itemById(OPEN)).isPromoted=True
        listen(_app.documentActivated,Activated())
        listen(_app.documentDeactivating,LeavingDocument())
        listen(_app.documentClosing,LeavingDocument())
        listen(_app.documentClosed,DocumentClosed())
        listen(_app.documentSaving,SavingDocument())
        if not isinstance(context,dict) or not context.get("IsApplicationStartup",False):show()
    except Exception:_ui.messageBox("UHV Chamber Builder could not start:\n"+traceback.format_exc())


def stop(context):
    global _pending,_busy,_stopping,_flush_queued,_custom_id,_cancel_requested
    global _bound_document,_doc_key,_recipe,_reload_pending,_operation_doc_key
    _stopping=True;_cancel_requested=True;clear_preview();end_progress();_pending=None;_busy=False
    _messages.clear();_flush_queued=False;_reload_pending=False
    _bound_document=None;_doc_key="";_recipe=None;_operation_doc_key=""
    for event,handler in reversed(_handlers):
        try:event.remove(handler)
        except Exception:pass
    _handlers.clear()
    if _ui:
        if palette():palette().deleteMe()
        panel=_ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
        if panel and panel.controls.itemById(OPEN):panel.controls.itemById(OPEN).deleteMe()
        for ident in (OPEN,EXEC):
            item=_ui.commandDefinitions.itemById(ident)
            if item:item.deleteMe()
    if _custom_id:
        try:_app.unregisterCustomEvent(_custom_id)
        except RuntimeError:pass
        _custom_id=""
