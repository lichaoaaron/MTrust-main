from mtrust.pipeline.pipeline import MTrustPipeline
pipeline = MTrustPipeline(spec_root="mtrust/specs")
print(pipeline.run("test"))
