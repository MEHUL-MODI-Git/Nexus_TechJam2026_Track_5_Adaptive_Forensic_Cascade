import json

import pytest
from PIL import Image

from scripts.prepare_smoke_dataset import build_manifest
from scripts.validate_smoke_manifest import validate


def _args(tmp_path, seed=7, count=2):
    class A: pass
    a=A(); a.real_dir=str(tmp_path/'real'); a.fake_dir=str(tmp_path/'fake'); a.seed=seed; a.count=count
    for k,v in {'dataset_real':'COCO','dataset_fake':'SID-Set','split_real':'train','split_fake':'fully_synthetic','revision_real':'r1','revision_fake':'r1','uri_real':'local','uri_fake':'local','group_real':'r','group_fake':'g','generator_fake':'gen','license_real':'COCO-TERMS','license_fake':'SID-CC-BY-4.0'}.items(): setattr(a,k,v)
    return a
def _imgs(tmp_path, n=3):
    for cls, color in [('real',(20,30,40)),('fake',(200,100,50))]:
        d=tmp_path/cls; d.mkdir()
        for i in range(n): Image.new('RGB',(10,8),(color[0]+i,color[1],color[2])).save(d/f'{i}.png')
def test_deterministic_balanced_and_schema(tmp_path):
    _imgs(tmp_path); a=_args(tmp_path); x=build_manifest(a); y=build_manifest(a)
    assert x==y and [r['label'] for r in x['images']].count(0)==2
    out=tmp_path/'m.json'; out.write_text(json.dumps(x)); assert validate(out,tmp_path)==[]
def test_val2017_rejected(tmp_path):
    _imgs(tmp_path); (tmp_path/'real'/'val2017.png').write_bytes((tmp_path/'real'/'0.png').read_bytes())
    a=_args(tmp_path); a.uri_real='COCO val2017';
    with pytest.raises(ValueError, match='val2017'): build_manifest(a)
def test_exact_duplicate_rejected(tmp_path):
    _imgs(tmp_path); (tmp_path/'fake'/'0.png').write_bytes((tmp_path/'real'/'0.png').read_bytes())
    with pytest.raises(ValueError, match='duplicate'): build_manifest(_args(tmp_path, count=3))
def test_schema_validation_rejects_hash_change(tmp_path):
    _imgs(tmp_path); out=tmp_path/'m.json'; out.write_text(json.dumps(build_manifest(_args(tmp_path))))
    d=json.loads(out.read_text()); d['images'][0]['original_sha256']='0'*64; out.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='SHA256'): validate(out,tmp_path)


def test_insufficient_class_count_is_not_silently_shortened(tmp_path):
    _imgs(tmp_path, n=1)
    with pytest.raises(ValueError, match="requested 2 images"):
        build_manifest(_args(tmp_path, count=2))


def test_label_class_mapping_is_enforced(tmp_path):
    _imgs(tmp_path)
    out = tmp_path / "m.json"
    doc = build_manifest(_args(tmp_path))
    row = doc["images"][0]
    row["class_name"] = "fully_synthetic" if row["label"] == 0 else "real"
    out.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="label/class"):
        validate(out, tmp_path)
