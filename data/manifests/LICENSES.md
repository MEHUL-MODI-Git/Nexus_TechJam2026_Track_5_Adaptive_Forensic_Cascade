# Smoke-manifest license inventory

The manifest records terms by stable `license_id`; raw datasets are not redistributed here.

| license_id | Source/terms | Redistribution |
|---|---|---|
| `COCO-TERMS` | [COCO terms of use](https://cocodataset.org/#termsofuse); smoke rows use the `train2017` split only | Do not redistribute here. COCO does not own the underlying Flickr images; each remains subject to its source terms. |
| `SID-CC-BY-4.0` | [SID-Set](https://huggingface.co/datasets/saberzl/SID_Set), revision `dc03ead57929879319ce30a82bfcfb8d317b10bd`, marked CC BY 4.0 | Attribution required; also respect any incorporated source-dataset terms. Raw images remain local and ignored. |

Local or future datasets must add a reviewed inventory row before entering a manifest.

The public SID-Set schema identifies fully synthetic rows (`label=1`) but does
not expose the originating generator. The Phase-0 smoke manifest therefore
uses a dataset-level `source_group`/`generator` value. These rows are suitable
for adapter separation smoke-testing only and must not be reused for the
generator-grouped router corpus without richer provenance.
