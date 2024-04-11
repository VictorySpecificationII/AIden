# AIden

World's best co-pilot.

# Deploy Infrastructure

Before deploying on a GCP Cloud, you need to create the project and attach it to a billing account first.
You cannot do that via Terraform.

After that, you need to enable the Google Compute Engine API for your project so you can run Terraform commands.

Run the following commands on your local box to get k3sup:

```
curl -sLS https://get.k3sup.dev | sh
sudo install k3sup /usr/local/bin/
k3sup version
```

Then run the following commands to login to gcloud CLI and deploy the cluster:

```
gcloud auth application-default login
gcloud auth application-default set-quota-project aiden-ai-copilot
terraform fmt
terraform validate
terraform plan
terraform apply
terraform show
```

After provisioning the master node, k3sup will automatically save locally a kubeconfig file in the same directory of main.tf file, which feeds the configuration for kubectl command.
