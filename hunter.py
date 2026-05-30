import os
import time
import sys
import oci

# Retrieve protected configuration from GitHub Secrets
COMPARTMENT_ID = os.environ.get("OCI_COMPARTMENT_ID")
SUBNET_ID = os.environ.get("OCI_SUBNET_ID")
IMAGE_ID = os.environ.get("OCI_IMAGE_ID")
SSH_PUBLIC_KEY = os.environ.get("OCI_SSH_PUBLIC_KEY")

config = {
    "user": os.environ.get("OCI_USER_OCID"),
    "key_content": os.environ.get("OCI_PRIVATE_KEY"),
    "fingerprint": os.environ.get("OCI_FINGERPRINT"),
    "tenancy": os.environ.get("OCI_TENANCY_OCID"),
    "region": "uk-london-1"  # Fixed to your locked London region
}

def main():
    try:
        core_client = oci.core.ComputeClient(config)
        identity_client = oci.identity.IdentityClient(config)
    except Exception as e:
        print(f"🚨 Configuration Error: {e}")
        sys.exit(1)

    try:
        ads = identity_client.list_availability_domains(COMPARTMENT_ID).data
        ad_names = [ad.name for ad in ads]
        print(f"Found Availability Domains: {ad_names}")
    except Exception as e:
        print(f"🚨 Failed to fetch Availability Domains: {e}")
        sys.exit(1)

    shape = "VM.Standard.A1.Flex"
    ocpus = 2.0          # Target resource size requested for n8n
    memory_in_gbs = 12.0 # Target resource size requested for n8n

    # This loop runs 5 times per trigger (spanning ~10 minutes total per run)
    for cycle in range(5):
        print(f"\n--- Starting Hunt Cycle {cycle + 1} of 5 ---")
        for ad in ad_names:
            print(f"Sniping for 2 Core / 12GB RAM (200GB SSD @ 120 VPU) in {ad}...")
            try:
                launch_details = oci.core.models.LaunchInstanceDetails(
                    compartment_id=COMPARTMENT_ID,
                    availability_domain=ad,
                    shape=shape,
                    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                        ocpus=ocpus,
                        memory_in_gbs=memory_in_gbs
                    ),
                    source_details=oci.core.models.InstanceSourceViaImageDetails(
                        source_type="image",
                        image_id=IMAGE_ID,
                        boot_volume_size_in_gbs=200,    # Forces the full 200GB allocation
                        boot_volume_vpus_per_gb=120     # Forces Ultra High Performance mode
                    ),
                    create_vnic_details=oci.core.models.CreateVnicDetails(
                        subnet_id=SUBNET_ID,
                        assign_public_ip=True,
                        display_name="n8n-Production-VNIC"
                    ),
                    metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
                    display_name="n8n-Automation-Server"
                )
                
                instance = core_client.launch_instance(launch_details)
                print(f"\n🎉 SUCCESS! Your server is provisioning!")
                print(f"Instance ID: {instance.data.id}")
                sys.exit(0)
                
            except oci.exceptions.ServiceError as e:
                if e.status == 429 or "Out of capacity" in e.message or "LimitExceeded" in e.code:
                    print(f"❌ AD Capacity dry. Moving onward...")
                elif "AlreadyExists" in e.code:
                    print("🎉 Success! The instance already exists or is building.")
                    sys.exit(0)
                else:
                    print(f"⚠️ OCI API Alert ({e.status}): {e.message}")
            except Exception as e:
                print(f"🚨 Unexpected Error: {e}")
        
        if cycle < 4:
            print("Sleeping 2 minutes before running next cycle...")
            time.sleep(120)

if __name__ == "__main__":
    main()
