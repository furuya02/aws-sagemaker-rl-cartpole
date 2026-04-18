import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as sagemaker from 'aws-cdk-lib/aws-sagemaker';

const PYTORCH_INFERENCE_IMAGE_URI =
  '763104351884.dkr.ecr.ap-northeast-1.amazonaws.com' +
  '/pytorch-inference:2.1.0-cpu-py310-ubuntu20.04-sagemaker';
const ENDPOINT_INSTANCE_TYPE = 'ml.m5.large';

export interface AwsSagemakerRlCartpoleModelStackProps extends cdk.StackProps {
  readonly executionRole: iam.IRole;
  readonly modelDataUrl: string;
}

// Model artifact layer: SageMaker Model + EndpointConfig (both free metadata).
// Depends on BaseStack (execution role) and a trained model.tar.gz URI (context).
// Endpoint itself is intentionally NOT created here so it can be started/stopped
// via scripts (scripts/start_endpoint.py / stop_endpoint.py) to control hourly cost.
export class AwsSagemakerRlCartpoleModelStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: AwsSagemakerRlCartpoleModelStackProps) {
    super(scope, id, props);

    const cartpoleModel = new sagemaker.CfnModel(this, 'CartPoleModel', {
      executionRoleArn: props.executionRole.roleArn,
      primaryContainer: {
        image: PYTORCH_INFERENCE_IMAGE_URI,
        modelDataUrl: props.modelDataUrl,
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
