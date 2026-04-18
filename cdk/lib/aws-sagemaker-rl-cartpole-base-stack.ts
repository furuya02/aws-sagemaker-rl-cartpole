import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';

const PROJECT_NAME = 'aws-sagemaker-rl-cartpole';

// Permanent infrastructure: S3 bucket + SageMaker execution role.
// These resources have near-zero cost and stay in place across training cycles.
export class AwsSagemakerRlCartpoleBaseStack extends cdk.Stack {
  public readonly artifactsBucket: s3.Bucket;
  public readonly sageMakerExecutionRole: iam.Role;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Bucket suffix defaults to AWS account ID for global uniqueness.
    // Override via `cdk deploy -c bucket_suffix=<value>` for fixed names
    // (e.g. blog screenshots without exposing the account ID).
    const bucketSuffix =
      (this.node.tryGetContext('bucket_suffix') as string | undefined) ?? this.account;

    this.artifactsBucket = new s3.Bucket(this, 'ArtifactsBucket', {
      bucketName: `${PROJECT_NAME}-${bucketSuffix}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    this.sageMakerExecutionRole = new iam.Role(this, 'SageMakerExecutionRole', {
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
                this.artifactsBucket.bucketArn,
                `${this.artifactsBucket.bucketArn}/*`,
              ],
            }),
          ],
        }),
      },
    });

    new cdk.CfnOutput(this, 'ArtifactsBucketName', {
      value: this.artifactsBucket.bucketName,
      description: 'S3 bucket for training input/output artifacts',
    });
    new cdk.CfnOutput(this, 'SageMakerExecutionRoleArn', {
      value: this.sageMakerExecutionRole.roleArn,
      description: 'IAM role ARN used by SageMaker training jobs and endpoints',
    });
  }
}
