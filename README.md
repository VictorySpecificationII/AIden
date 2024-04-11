# AIden

World's best co-pilot.

# Deploy Infrastructure

Before deploying on a GCP Cloud, you need to create the project and attach it to a billing account first.
You cannot do that via Terraform.

After that, you need to enable the Google Compute Engine API for your project so you can run Terraform commands.
Then:

 - gcloud auth application-default login
 - gcloud auth application-default set-quota-project aiden-ai-copilot
 - terraform fmt
 - terraform validate
 - terraform plan
 - terraform apply
 - terraform show
