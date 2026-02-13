terraform {
  source = "../../"
}

include "root" {
  path = find_in_parent_folders("root.hcl")
}

inputs = {
  project_id       = "openclaw-antonmishel-03460"
  region           = "us-west1"
  cluster_name     = "vancity-lens-dev"
  environment_name = "dev"
}
