#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AwsSagemakerRlCartpoleBaseStack } from '../lib/aws-sagemaker-rl-cartpole-base-stack';
import { AwsSagemakerRlCartpoleModelStack } from '../lib/aws-sagemaker-rl-cartpole-model-stack';

const app = new cdk.App();

const targetRegion: string = process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1';
const targetAccount: string | undefined = process.env.CDK_DEFAULT_ACCOUNT;
const env = { account: targetAccount, region: targetRegion };

// Always instantiated: permanent S3 / IAM layer.
const baseStack = new AwsSagemakerRlCartpoleBaseStack(
  app,
  'AwsSagemakerRlCartpoleBaseStack',
  { env },
);

// Instantiated only when `-c model_data_url=<s3 URI>` is passed.
// For `cdk destroy` after deployment, any value (e.g. `placeholder`) is fine —
// CDK only needs the stack to be visible in the app to locate it for deletion.
const modelDataUrl = app.node.tryGetContext('model_data_url') as string | undefined;
if (modelDataUrl) {
  new AwsSagemakerRlCartpoleModelStack(app, 'AwsSagemakerRlCartpoleModelStack', {
    env,
    executionRole: baseStack.sageMakerExecutionRole,
    modelDataUrl,
  });
}
