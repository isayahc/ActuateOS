#!/usr/bin/env python3
"""Convert original IndustReal 3MF mesh sets to OpenIndustries asset inputs."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

DATA = Path(__file__).resolve().parents[1] / "data" / "industreal"
CATEGORIES = {
    "Beams Braces": ("beams-braces", "Original beams & braces set", [.85,.85,.79]),
    "Screws Pins": ("screws-pins", "Original screws & pins set", [.55,.59,.63]),
    "Sign Nuts Washers Pulley": ("nuts-washers-pulley", "Original nuts, washers & pulley set", [.77,.2,.48]),
    "Wheels": ("wheels", "Original wheel set", [.12,.13,.15]),
}


def prepare():
    assets, catalog = [], []
    for category, (asset_id, name, color) in CATEGORIES.items():
        file = next(DATA.glob(f"* - {category}.3mf"))
        with zipfile.ZipFile(file) as source:
            model = next(n for n in source.namelist() if n.lower().endswith(".model"))
            root = ET.fromstring(source.read(model))
        ns = {"m": root.tag.split("}")[0][1:]}
        if root.get("unit") != "millimeter":
            raise ValueError("Unexpected 3MF units")
        objects = root.findall("m:resources/m:object", ns)
        if len(objects) != 1 or objects[0].find("m:mesh", ns) is None:
            raise ValueError("This adapter expects the dataset's single-mesh print sets")
        # Preserve source mesh topology; millimeters -> meters and the documented 200% print scale.
        # 3MF Z-up becomes OI Y-up with a proper rotation (x,z,-y).
        vertices = []
        for vertex in objects[0].findall("m:mesh/m:vertices/m:vertex", ns):
            x,y,z = (float(vertex.attrib[k])*.002 for k in ("x","y","z"))
            vertices.extend([round(x,7),round(z,7),round(-y,7)])
        indices = [int(triangle.attrib[k]) for triangle in objects[0].findall("m:mesh/m:triangles/m:triangle", ns) for k in ("v1","v2","v3")]
        mins = [min(vertices[axis::3]) for axis in range(3)]
        maxs = [max(vertices[axis::3]) for axis in range(3)]
        dimensions = [round(b-a,5) for a,b in zip(mins,maxs)]
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        part_id = f"{asset_id}/original-mesh"
        assets.append({"id":asset_id,"name":name,
            "source":{"kind":"generated","filename":file.name,"digest":digest,"generator":"oi-fixture"},
            "parts":[{"id":part_id,"name":name,"vertices":vertices,"indices":indices,"color":color,
                      "metadata":{"source":"IndustReal v2 original 3MF","scale":"0.002 m/source mm (200% print scale)","representation":"Original multi-component print-set mesh, not an assembled car"}}],
            "hierarchy":{"id":asset_id+"/root","name":name,"partIds":[part_id],"children":[]},
            "warnings":["Source print-set layout retained; no individual-part semantic segmentation.","Workcell placement is proposed, not measured from the recording."]})
        catalog.append({"id":asset_id,"name":name,"dimensions_m":dimensions,"source_file":file.name,
                        "description":"Genuine dataset multi-part print set. Place on a table as parts inventory; not an assembled car."})
    (DATA/"geometry.json").write_text(json.dumps({"assets":assets}, separators=(",",":")))
    (DATA/"geometry-catalog.json").write_text(json.dumps(catalog,indent=2)+"\n")
    print(f"Converted {len(assets)} source geometry sets")


if __name__ == "__main__":
    prepare()
