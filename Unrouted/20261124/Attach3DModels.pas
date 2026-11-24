{ ============================================================================
  Attach3DModels.pas  -  Altium Designer DelphiScript (Smash, 2026-11-23)

  Altium's KiCad importer drops footprint 3D models. This script puts them
  back: it reads the model map exported next to each KiCad project
  (3D_MODEL_MAP_altium.txt) and embeds each footprint's STEP as a 3D body in
  the CURRENTLY OPEN PCB LIBRARY, with KiCad's rotation and offset.

  HOW TO USE
    1. Import the KiCad project as usual. Open the imported PcbDoc and make a
       library from it:  Design > Make PCB Library  (opens a .PcbLib).
    2. With that PcbLib as the active document:  File > Run Script... >
       Attach3DModels.pas > RunAttach3DModels
       (or DXP/File > Scripting > Run Script; add this .pas to a script
       project if your Altium version asks for one).
    3. Pick the map file: 3D_MODEL_MAP_altium.txt in the project's folder
       (dev_board\ for the dev board, the export root for the tower).
       STEP paths in the map are relative to that file's folder.
    4. Read the summary (attached / skipped / not found), save the PcbLib, then
       in the PcbLib:  Tools > Update PCB With All  to push the bodies into
       the board (Altium handles position, rotation and bottom-side flip).

  CHECK AFTER THE FIRST RUN (untested against your Altium version)
    * Rotation sign: KiCad applies model rotations with negated angles (our
      LTC3124 uses -90 deg about X to stand a Y-up STEP upright). The script
      therefore negates them (ROT_SIGN = -1). If parts lie on their side or
      upside down, set ROT_SIGN := 1 below, delete the added bodies (they are
      on MECH_LAYER) and run again.
    * Footprints rotated about TWO axes are listed in the summary - check those
      in the 3D view (rotation order may differ between KiCad and Altium).
    * Footprints that already have a 3D body are skipped (re-run safe).
  ============================================================================ }

const
  ROT_SIGN   = -1;            // KiCad -> Altium rotation sign (see above)
  MECH_LAYER = eMechanical13; // layer for the added 3D bodies

var
  Summary : TStringList;

function NumOf(S : String) : Double;
var
  T : String;
begin
  T := Trim(S);
  if T = '' then T := '0';
  // map files always use '.' as decimal separator
  if DecimalSeparator <> '.' then T := StringReplace(T, '.', DecimalSeparator, -1);
  Result := StrToFloat(T);
end;

function BareName(S : String) : String;
var
  P : Integer;
begin
  // KiCad library prefix "Lib:Name" -> "Name"; Altium may keep or drop it
  P := Pos(':', S);
  if P > 0 then Result := Copy(S, P + 1, Length(S)) else Result := S;
  Result := UpperCase(Trim(Result));
end;

procedure SplitTabs(Line : String; Parts : TStringList);
var
  P : Integer;
begin
  Parts.Clear;
  P := Pos(#9, Line);
  while P > 0 do
  begin
    Parts.Add(Copy(Line, 1, P - 1));
    Line := Copy(Line, P + 1, Length(Line));
    P := Pos(#9, Line);
  end;
  Parts.Add(Line);
end;

function HasBody(Footprint : IPCB_LibComponent) : Boolean;
var
  It  : IPCB_GroupIterator;
  Obj : IPCB_Primitive;
begin
  Result := False;
  It := Footprint.GroupIterator_Create;
  It.AddFilter_ObjectSet(MkSet(eComponentBodyObject));
  Obj := It.FirstPCBObject;
  if Obj <> nil then Result := True;
  Footprint.GroupIterator_Destroy(It);
end;

procedure RunAttach3DModels;
var
  Lib       : IPCB_Library;
  Dlg       : TOpenDialog;
  MapFile, BaseDir, Line, StepPath, FpName : String;
  MapLines, Parts : TStringList;
  Names, Rows : TStringList;
  LibIt     : IPCB_LibraryIterator;
  Footprint : IPCB_LibComponent;
  Body      : IPCB_ComponentBody;
  Model     : IPCB_Model;
  I, Idx, nOk, nSkip, nMiss, nNoMap : Integer;
  ox, oy, oz, rx, ry, rz : Double;
  TwoAxis   : String;
begin
  Lib := PCBServer.GetCurrentPCBLibrary;
  if Lib = nil then
  begin
    ShowMessage('Open the PCB LIBRARY (Design > Make PCB Library from the imported PcbDoc) and run again.');
    Exit;
  end;

  Dlg := TOpenDialog.Create(nil);
  Dlg.Title  := 'Select 3D_MODEL_MAP_altium.txt';
  Dlg.Filter := 'Model map (*.txt)|*.txt';
  if not Dlg.Execute then Exit;
  MapFile := Dlg.FileName;
  BaseDir := ExtractFilePath(MapFile);

  MapLines := TStringList.Create;
  MapLines.LoadFromFile(MapFile);
  Names := TStringList.Create;   // footprint name (upper case, no lib prefix)
  Rows  := TStringList.Create;   // the matching map line
  for I := 0 to MapLines.Count - 1 do
  begin
    Line := MapLines[I];
    if (Trim(Line) = '') or (Copy(Line, 1, 1) = '#') then Continue;
    Parts := TStringList.Create;
    SplitTabs(Line, Parts);
    if Parts.Count >= 8 then
    begin
      Names.Add(BareName(Parts[0]));
      Rows.Add(Line);
    end;
    Parts.Free;
  end;

  Summary := TStringList.Create;
  nOk := 0; nSkip := 0; nMiss := 0; nNoMap := 0; TwoAxis := '';
  PCBServer.PreProcess;

  LibIt := Lib.LibraryIterator_Create;
  LibIt.SetState_FilterAll;
  Footprint := LibIt.FirstPCBObject;
  while Footprint <> nil do
  begin
    FpName := Footprint.Name;
    Idx := Names.IndexOf(BareName(FpName));
    if Idx < 0 then
    begin
      Inc(nNoMap);
      Summary.Add('no map entry : ' + FpName);
    end
    else if HasBody(Footprint) then
      Inc(nSkip)
    else
    begin
      Parts := TStringList.Create;
      SplitTabs(Rows[Idx], Parts);
      StepPath := BaseDir + Parts[1];
      ox := NumOf(Parts[2]); oy := NumOf(Parts[3]); oz := NumOf(Parts[4]);
      rx := NumOf(Parts[5]); ry := NumOf(Parts[6]); rz := NumOf(Parts[7]);
      Parts.Free;
      if not FileExists(StepPath) then
      begin
        Inc(nMiss);
        Summary.Add('STEP missing : ' + FpName + '  ->  ' + StepPath);
      end
      else
      begin
        Body := PCBServer.PCBObjectFactory(eComponentBodyObject, eNoDimension, eCreate_Default);
        Model := Body.ModelFactory_FromFilename(StepPath, False);   // False = embed in the library
        if Model = nil then
        begin
          Inc(nMiss);
          Summary.Add('STEP not loadable : ' + FpName + '  ->  ' + StepPath);
        end
        else
        begin
          Model.SetState(ROT_SIGN * rx, ROT_SIGN * ry, ROT_SIGN * rz, MMsToCoord(oz));
          Body.Model := Model;
          Body.SetState_FromModel;
          Body.Layer := MECH_LAYER;
          Body.BodyProjection := eBoardSide_Top;
          // footprint origin + KiCad XY offset (both y-up)
          Body.MoveToXY(Lib.Board.XOrigin + MMsToCoord(ox), Lib.Board.YOrigin + MMsToCoord(oy));
          Footprint.AddPCBObject(Body);
          PCBServer.SendMessageToRobots(Footprint.I_ObjectAddress, c_Broadcast,
                                        PCBM_BoardRegisteration, Body.I_ObjectAddress);
          Inc(nOk);
          if ((rx <> 0) and (ry <> 0)) or ((rx <> 0) and (rz <> 0)) or ((ry <> 0) and (rz <> 0)) then
            TwoAxis := TwoAxis + '  ' + FpName + #13#10;
        end;
      end;
    end;
    Footprint := LibIt.NextPCBObject;
  end;
  Lib.LibraryIterator_Destroy(LibIt);

  PCBServer.PostProcess;
  Lib.Board.ViewManager_FullUpdate;

  Line := 'Attached: ' + IntToStr(nOk) + '   already had a body: ' + IntToStr(nSkip) +
          '   STEP missing: ' + IntToStr(nMiss) + '   no map entry: ' + IntToStr(nNoMap) + #13#10;
  if TwoAxis <> '' then
    Line := Line + #13#10 + 'Rotated about two axes - check these in 3D:' + #13#10 + TwoAxis;
  if Summary.Count > 0 then
  begin
    Summary.SaveToFile(BaseDir + 'Attach3DModels_log.txt');
    Line := Line + #13#10 + 'Details: ' + BaseDir + 'Attach3DModels_log.txt';
  end;
  ShowMessage(Line + #13#10 + 'Save the library, then Tools > Update PCB With All.');

  Summary.Free; MapLines.Free; Names.Free; Rows.Free;
end;
