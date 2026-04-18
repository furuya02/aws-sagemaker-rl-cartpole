import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';

const PROJECT_NAME = 'aws-sagemaker-rl-cartpole';
const PYTORCH_INFERENCE_IMAGE_URI =
  '763104351884.dkr.ecr.ap-northeast-1.amazonaws.com' +
  '/pytorch-inference:2.1.0-cpu-py310-ubuntu20.04-sagemaker';
const ENDPOINT_INSTANCE_TYPE = 'ml.m5.large';

export class AwsSagemakerRlCartpoleStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Bucket suffix defaults to the AWS account ID (globally unique).
    // Override via `cdk deploy -c bucket_suffix=<value>` for cases where the
    // name should be fixed (e.g. blog screenshots without exposing account ID).
    const bucketSuffix =
      (this.node.tryGetContext('bucket_suffix') as string | undefined) ?? this.account;

    const artifactsBucket = new s3.Bucket(this, 'ArtifactsBucket', {
      bucketName: `${PROJECT_NAME}-${bucketSuffix}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    const sageMakerExecutionRole = new iam.Role(this, 'SageMakerExecutionRole', {
      roleName: `${PROJECT_NAME}-sagemaker-execution-role`,
      assumedBy: new iam.ServicePrincipal('sagemaker.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSageMakerFullAccess'),
      ],
      inlinePolicies: {
        [`${PROJECT_NAME}-sagemaker-s3-rw-policy`]: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                's3:GetObject*',
                's3:GetBucket*',
                's3:List*',
                's3:DeleteObject*',
                's3:PutObject*',
                's3:Abort*',
              ],
              resources: [
                artifactsBucket.bucketArn,
                `${artifactsBucket.bucketArn}/*`,
              ],
            }),
          ],
        }),
      },
    });

    new cdk.CfnOutput(this, 'ArtifactsBucketName', {
      value: artifactsBucket.bucketName,
      description: 'S3 bucket for training input/output artifacts',
    });
    new cdk.CfnOutput(this, 'SageMakerExecutionRoleArn', {
      value: sageMakerExecutionRole.roleArn,
      description: 'IAM role ARN used by SageMaker training jobs and endpoints',
    });

    const modelDataUrl = this.node.tryGetContext('model_data_url') as string | undefined;
    if (modelDataUrl) {
      this.createModelAndEndpointConfig(modelDataUrl, sageMakerExecutionRole);
    }
  }

  // Endpoint itself is intentionally NOT created by CDK so it can be started/stopped
  // via scripts (scripts/start_endpoint.py / stop_endpoint.py) to control hourly cost.
  private createModelAndEndpointConfig(modelDataUrl: string, executionRole: iam.Role): void {
    const cartpoleModel = new sagemaker.CfnModel(this, 'CartPoleModel', {
      executionRoleArn: executionRole.roleArn,
      primaryContainer: {
        image: PYTORCH_INFERENCE_IMAGE_URI,
        modelDataUrl: modelDataUrl,
        environment: {
          SAGEMAKER_PROGRAM: 'inference.py',
          SAGEMAKER_SUBMIT_DIRECTORY: '/opt/ml/model/code',
          SAGEMAKER_CONTAINER_LOG_LEVEL: '20',
        },
      },
    });

    const endpointConfig = new sagemaker.CfnEndpointConfig(this, 'CartPoleEndpointConfig', {
      productionVariants: [
        {
          modelName: cartpoleModel.attrModelName,
          variantName: 'AllTraffic',
          initialInstanceCount: 1,
          instanceType: ENDPOINT_INSTANCE_TYPE,
          initialVariantWeight: 1.0,
        },
      ],
    });
    endpointConfig.addDependency(cartpoleModel);

    new cdk.CfnOutput(this, 'CartPoleEndpointConfigName', {
      value: endpointConfig.attrEndpointConfigName,
      description: 'SageMaker EndpointConfig name. Pass to scripts/start_endpoint.py to provision an endpoint.',
    });
  }
}
