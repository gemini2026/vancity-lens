terraform {
  source = "../../"
}

include "root" {
  path = find_in_parent_folders("terragrunt.hcl")
}

include "env" {
  path = find_in_parent_folders("env.hcl")
}

inputs = {
  project_id   = "openclaw-antonmishel-03460"
  region       = "us-west1"
  cluster_name = "vancity-lens-dev"
}
